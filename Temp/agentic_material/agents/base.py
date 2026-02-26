from __future__ import annotations

import ast
import json
import logging
import os
import re
import threading
import time
from urllib.parse import quote_plus
from typing import Any

from ..config import Settings

try:
    from crewai import Agent, Crew, Process, Task
except Exception:  # pragma: no cover - optional runtime dependency
    Agent = Crew = Process = Task = None  # type: ignore[assignment]

try:
    import litellm  # type: ignore

    LITELLM_AVAILABLE = True
except Exception:  # pragma: no cover - optional runtime dependency
    litellm = None  # type: ignore
    LITELLM_AVAILABLE = False

try:
    from langchain_groq import ChatGroq
except Exception:  # pragma: no cover - optional runtime dependency
    ChatGroq = None  # type: ignore[assignment]

logger = logging.getLogger("uvicorn.error")


class BaseStructuredAgent:
    _llm_semaphore_lock = threading.Lock()
    _llm_semaphore: threading.BoundedSemaphore | None = None
    _llm_semaphore_size: int | None = None

    def __init__(
        self,
        settings: Settings,
        *,
        role: str,
        goal: str,
        backstory: str,
        temperature: float = 0.2,
    ) -> None:
        self.settings = settings
        self.role = role
        self.goal = goal
        self.backstory = backstory
        self.temperature = temperature
        self._chat_llm = None
        self._chat_llm_json = None
        self._chat_llm_json_disabled = False
        self._crewai_model = self._normalize_crewai_model(settings.groq_model)
        self._crewai_disabled = False
        self._crewai_enabled = settings.enable_crewai_execution
        self._last_llm_error: str | None = None
        if settings.groq_api:
            # CrewAI/LiteLLM expects provider-specific env key for Groq.
            os.environ["GROQ_API_KEY"] = settings.groq_api
            os.environ.setdefault("GROQ_API", settings.groq_api)
        if ChatGroq and settings.groq_api:
            self._chat_llm = ChatGroq(
                model=settings.groq_model,
                groq_api_key=settings.groq_api,
                temperature=temperature,
                max_retries=4,
                timeout=settings.request_timeout_seconds,
            )
            self._chat_llm_json = ChatGroq(
                model=settings.groq_model,
                groq_api_key=settings.groq_api,
                temperature=0.0,
                max_retries=2,
                timeout=settings.request_timeout_seconds,
                model_kwargs={"response_format": {"type": "json_object"}},
            )
        self._ensure_llm_semaphore(settings.llm_max_concurrency)

    def run_json_task(
        self,
        prompt: str,
        *,
        expected_output: str = "Strict JSON only.",
        required_keys: list[str] | None = None,
    ) -> dict[str, Any]:
        failures: list[str] = []
        retries = max(self.settings.agent_retry_attempts, 1)
        for attempt in range(1, retries + 1):
            try:
                with self._acquire_llm_slot():
                    result = self._run_with_chat_json(prompt)
                    if result is None:
                        result = self._run_with_chat(prompt)
                    if result is None:
                        result = self._run_with_crewai(prompt=prompt, expected_output=expected_output)
                    if result is None:
                        result = self._run_with_litellm(prompt=prompt)
                if result is None:
                    raise ValueError("No JSON output returned by model path.")
                self._validate_required_keys(result, required_keys)
                return result
            except Exception as exc:
                failures.append(f"attempt {attempt}: {exc}")
                # If no model path produced any payload at all, waiting for more retries
                # usually adds delay without improving output.
                if "No JSON output returned by model path." in str(exc):
                    break
                if attempt < retries:
                    time.sleep(min(2**(attempt - 1), 4))
        if self.settings.enable_fallback_content:
            fallback = self._build_fallback_payload(prompt=prompt, required_keys=required_keys)
            if fallback is not None:
                logger.warning(
                    "[AgentFallback:%s] Using structured fallback content after model failures: %s",
                    self.role,
                    " | ".join(failures) if failures else "no model output",
                )
                return fallback
        if not failures and self._last_llm_error:
            failures.append(self._last_llm_error)
        if not failures:
            failures.append(self._diagnose_missing_llm_paths())
        raise ValueError(f"{self.role} failed to produce valid structured output. {' | '.join(failures)}")

    def _run_with_crewai(self, *, prompt: str, expected_output: str) -> dict[str, Any] | None:
        if not self._crewai_enabled:
            return None
        if self._crewai_disabled:
            return None
        if not LITELLM_AVAILABLE:
            return None
        if not self._crewai_model or not Agent or not Crew or not Task or not Process:
            return None
        try:
            agent = Agent(
                role=self.role,
                goal=self.goal,
                backstory=self.backstory,
                llm=self._crewai_model,
                verbose=False,
                allow_delegation=False,
            )
            task = Task(
                description=f"{prompt}\nReturn JSON only without markdown fences.",
                expected_output=expected_output,
                agent=agent,
            )
            crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
            output = crew.kickoff()
            raw = getattr(output, "raw", str(output))
            return self._extract_json(raw)
        except Exception as exc:
            # Disable repeated failing CrewAI path and use Groq direct fallback.
            self._crewai_disabled = True
            self._last_llm_error = f"CrewAI execution failed: {exc}"
            logger.warning("[AgentLLM:%s] CrewAI execution failed: %s", self.role, exc)
            return None

    def _run_with_chat(self, prompt: str) -> dict[str, Any] | None:
        if not self._chat_llm:
            if self.settings.groq_api and ChatGroq is None:
                self._last_llm_error = "langchain_groq not available; ChatGroq client not initialized."
            return None
        try:
            response = self._chat_llm.invoke(prompt)
            content = getattr(response, "content", None)
            if isinstance(content, list):
                content = "".join(
                    str(part.get("text", part)) if isinstance(part, dict) else str(part)
                    for part in content
                )
            if not isinstance(content, str):
                content = str(content)
            try:
                return self._extract_json(content)
            except Exception as exc:
                snippet = content.replace("\n", " ").strip()
                if len(snippet) > 500:
                    snippet = f"{snippet[:500]}..."
                self._last_llm_error = f"ChatGroq produced non-JSON output: {exc}"
                logger.warning(
                    "[AgentLLM:%s] ChatGroq returned non-JSON output (snippet): %s",
                    self.role,
                    snippet,
                )
                return None
        except Exception as exc:
            self._last_llm_error = f"ChatGroq request failed: {exc}"
            logger.warning("[AgentLLM:%s] ChatGroq request failed: %s", self.role, exc)
            return None

    def _run_with_chat_json(self, prompt: str) -> dict[str, Any] | None:
        if not self._chat_llm_json or self._chat_llm_json_disabled:
            return None
        try:
            response = self._chat_llm_json.invoke(
                f"{prompt}\n\nReturn only strict JSON. Do not include any extra text."
            )
            content = getattr(response, "content", None)
            if isinstance(content, list):
                content = "".join(
                    str(part.get("text", part)) if isinstance(part, dict) else str(part)
                    for part in content
                )
            if not isinstance(content, str):
                content = str(content)
            try:
                return self._extract_json(content)
            except Exception as exc:
                snippet = content.replace("\n", " ").strip()
                if len(snippet) > 500:
                    snippet = f"{snippet[:500]}..."
                self._last_llm_error = f"ChatGroq JSON-mode produced non-JSON output: {exc}"
                logger.warning(
                    "[AgentLLM:%s] ChatGroq JSON-mode returned non-JSON output (snippet): %s",
                    self.role,
                    snippet,
                )
                return None
        except Exception as exc:
            message = str(exc)
            if "response_format" in message or "json_object" in message:
                self._chat_llm_json_disabled = True
            self._last_llm_error = f"ChatGroq JSON-mode request failed: {exc}"
            logger.warning("[AgentLLM:%s] ChatGroq JSON-mode failed: %s", self.role, exc)
            return None

    def _run_with_litellm(self, prompt: str) -> dict[str, Any] | None:
        if not LITELLM_AVAILABLE or not self.settings.groq_api:
            return None
        try:
            response = litellm.completion(
                model=self._crewai_model,
                messages=[
                    {"role": "system", "content": "Return JSON only without markdown fences."},
                    {"role": "user", "content": prompt},
                ],
                temperature=self.temperature,
                timeout=self.settings.request_timeout_seconds,
                api_key=self.settings.groq_api,
            )
            content: Any = None
            if isinstance(response, dict):
                choices = response.get("choices") or []
                if choices:
                    message = choices[0].get("message") or {}
                    content = message.get("content") or choices[0].get("text")
            else:
                choices = getattr(response, "choices", None)
                if choices:
                    message = getattr(choices[0], "message", None)
                    if message is not None:
                        content = getattr(message, "content", None)
                    if content is None:
                        content = getattr(choices[0], "text", None)
            if content is None:
                raise ValueError("LiteLLM returned empty content.")
            return self._extract_json(str(content))
        except Exception as exc:
            self._last_llm_error = f"LiteLLM request failed: {exc}"
            logger.warning("[AgentLLM:%s] LiteLLM request failed: %s", self.role, exc)
            return None

    def _build_fallback_payload(self, *, prompt: str, required_keys: list[str] | None) -> dict[str, Any] | None:
        if required_keys is None:
            return {}

        concept_name = self._extract_prompt_value(prompt, ["Concept", "Concept Name"]) or "the concept"
        subject_name = self._extract_prompt_value(prompt, ["Subject"]) or "the subject"
        grade_level = self._extract_prompt_value(prompt, ["Grade Level"]) or "the target grade"

        payload: dict[str, Any] = {}
        for key in required_keys:
            normalized = key.strip().lower()
            if normalized in {"objectives", "prerequisites", "misconceptions"}:
                payload[key] = self._fallback_list(normalized, concept_name, subject_name, grade_level)
                continue
            if normalized in {"lesson_flow", "teaching_tips", "key_steps", "common_mistakes", "recap", "examples"}:
                payload[key] = self._fallback_list(normalized, concept_name, subject_name, grade_level)
                continue
            if normalized == "definition":
                payload[key] = (
                    f"{concept_name} is an essential part of {subject_name} where students learn core ideas at {grade_level} level."
                )
                continue
            if normalized == "intuition":
                payload[key] = (
                    f"Think of {concept_name} as a practical way to explain how a small rule creates larger patterns in real learning contexts."
                )
                continue
            if normalized == "mcqs":
                payload[key] = self._fallback_mcqs(concept_name)
                continue
            if normalized == "flashcards":
                payload[key] = self._fallback_flashcards(concept_name)
                continue
            if normalized == "references":
                payload[key] = self._fallback_references(concept_name, subject_name)
                continue
            if normalized == "approved":
                payload[key] = True
                continue
            if normalized in {"issues", "guidance"}:
                payload[key] = []
                continue

            payload[key] = self._fallback_generic_value(concept_name, key)

        return payload

    @staticmethod
    def _extract_prompt_value(prompt: str, field_names: list[str]) -> str | None:
        for name in field_names:
            pattern = rf"(?im)^\s*{re.escape(name)}\s*:\s*(.+?)\s*$"
            match = re.search(pattern, prompt)
            if match:
                value = match.group(1).strip().strip("\"'")
                if value and value.lower() not in {"none", "n/a"}:
                    return value
        return None

    @staticmethod
    def _fallback_list(kind: str, concept_name: str, subject_name: str, grade_level: str) -> list[str]:
        if kind == "objectives":
            return [
                f"Identify the main idea behind {concept_name}.",
                f"Explain {concept_name} in simple words suitable for {grade_level}.",
                f"Apply {concept_name} in short classroom-style examples.",
            ]
        if kind == "prerequisites":
            return [
                f"Basic vocabulary from {subject_name}.",
                "Comfort with reading short definitions.",
                "Ability to follow step-by-step reasoning.",
            ]
        if kind == "misconceptions":
            return [
                f"Confusing {concept_name} with unrelated topics.",
                "Memorizing terms without understanding usage.",
                "Skipping foundational definitions.",
            ]
        if kind == "lesson_flow":
            return [
                f"Start with a concrete definition of {concept_name}.",
                "Use one guided example with teacher explanation.",
                "Move to one independent attempt with feedback.",
                "Close with a short recap and quick check.",
            ]
        if kind == "teaching_tips":
            return [
                "Use short sentences and concrete terms.",
                "Check understanding after each step.",
                "Connect examples to familiar student contexts.",
            ]
        if kind == "key_steps":
            return [
                f"State the rule or definition of {concept_name}.",
                "Break the process into small ordered steps.",
                "Verify the result using a quick self-check.",
            ]
        if kind == "common_mistakes":
            return [
                "Skipping the first setup step.",
                "Applying a rule in the wrong order.",
                "Not checking the final answer.",
            ]
        if kind == "recap":
            return [
                f"{concept_name} has a clear definition, method, and practice pattern.",
                "Strong understanding comes from repeated short practice.",
                "Accuracy improves when each step is verified.",
            ]
        if kind == "examples":
            return [
                f"Example 1: Basic introduction to {concept_name} with one solved step.",
                f"Example 2: Intermediate use of {concept_name} with two solved steps.",
                f"Example 3: Application-style question on {concept_name} with final verification.",
            ]
        return [f"Core point about {concept_name}.", "Second supporting point.", "Third supporting point."]

    @staticmethod
    def _fallback_mcqs(concept_name: str) -> list[dict[str, Any]]:
        mcqs: list[dict[str, Any]] = []
        for index in range(1, 7):
            answer = f"Option A{index}"
            mcqs.append(
                {
                    "question": f"{concept_name}: Which choice best matches the core idea in question {index}?",
                    "options": [answer, f"Option B{index}", f"Option C{index}", f"Option D{index}"],
                    "answer": answer,
                    "explanation": f"{answer} directly reflects the correct interpretation of {concept_name}.",
                }
            )
        return mcqs

    @staticmethod
    def _fallback_flashcards(concept_name: str) -> list[dict[str, str]]:
        return [
            {
                "question": f"What is {concept_name}?",
                "answer": f"{concept_name} is a foundational topic explained with clear definitions and short examples.",
            },
            {
                "question": f"Why is {concept_name} important?",
                "answer": "It helps students build a reliable base before moving to advanced applications.",
            },
            {
                "question": f"What is one common mistake in {concept_name}?",
                "answer": "Skipping intermediate steps and rushing to the final answer.",
            },
            {
                "question": f"How should students practice {concept_name}?",
                "answer": "Practice short sets regularly and verify each step.",
            },
            {
                "question": f"What should be checked after solving a {concept_name} problem?",
                "answer": "Check whether the method and final result are consistent.",
            },
            {
                "question": f"How can {concept_name} be revised quickly?",
                "answer": "Review definition, 3 key steps, and one solved example.",
            },
            {
                "question": f"What type of examples help in {concept_name} learning?",
                "answer": "Examples that move from easy to medium difficulty.",
            },
            {
                "question": f"What improves confidence in {concept_name}?",
                "answer": "Frequent recall practice with feedback.",
            },
        ]

    @staticmethod
    def _fallback_references(concept_name: str, subject_name: str) -> list[dict[str, str]]:
        query = quote_plus(f"{subject_name} {concept_name}")
        return [
            {
                "title": "Khan Academy",
                "url": f"https://www.khanacademy.org/search?page_search_query={query}",
                "note": f"Free lessons and exercises related to {concept_name}.",
            },
            {
                "title": "CK-12",
                "url": f"https://www.ck12.org/search/?q={query}",
                "note": "Open educational content with concept-level explanations.",
            },
            {
                "title": "Wikipedia",
                "url": f"https://en.wikipedia.org/wiki/{quote_plus(concept_name).replace('+', '_')}",
                "note": "Quick reference article for basic terminology and overview.",
            },
        ]

    @staticmethod
    def _fallback_generic_value(concept_name: str, key: str) -> Any:
        lower_key = key.lower()
        if lower_key.endswith("s"):
            return [f"{concept_name} {key} item 1", f"{concept_name} {key} item 2"]
        return f"{concept_name} {key}"

    @classmethod
    def _ensure_llm_semaphore(cls, llm_max_concurrency: int) -> None:
        concurrency = max(1, llm_max_concurrency)
        with cls._llm_semaphore_lock:
            if cls._llm_semaphore is None or cls._llm_semaphore_size != concurrency:
                cls._llm_semaphore = threading.BoundedSemaphore(concurrency)
                cls._llm_semaphore_size = concurrency

    @classmethod
    def _acquire_llm_slot(cls):
        if cls._llm_semaphore is None:
            cls._llm_semaphore = threading.BoundedSemaphore(1)
        return cls._llm_semaphore

    @staticmethod
    def _validate_required_keys(payload: dict[str, Any], required_keys: list[str] | None) -> None:
        if not required_keys:
            return
        missing = [key for key in required_keys if key not in payload or payload[key] in (None, "", [], {})]
        if missing:
            raise ValueError(f"Missing required keys: {missing}")

    @staticmethod
    def _extract_json(raw: str) -> dict[str, Any]:
        text = raw.strip()
        try:
            value = json.loads(text)
            if isinstance(value, dict):
                return value
            raise ValueError("JSON output is not an object.")
        except Exception:
            pass

        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Unable to parse JSON from agent output.")
        chunk = text[start : end + 1]
        chunk = re.sub(r"^```json|```$", "", chunk, flags=re.MULTILINE).strip()
        try:
            value = json.loads(chunk)
            if isinstance(value, dict):
                return value
            raise ValueError("JSON output is not an object.")
        except Exception:
            try:
                value = ast.literal_eval(chunk)
                if isinstance(value, dict):
                    return value
            except Exception:
                pass
        raise ValueError("Unable to parse JSON from agent output.")

    def _diagnose_missing_llm_paths(self) -> str:
        reasons: list[str] = []
        if not self.settings.groq_api:
            reasons.append("GROQ_API/GROQ_API_KEY is not configured")
        if not self._chat_llm:
            if ChatGroq is None:
                reasons.append("langchain_groq is not installed")
            else:
                reasons.append("ChatGroq client is unavailable")
        if not LITELLM_AVAILABLE:
            reasons.append("LiteLLM is not installed")
        if not self._crewai_enabled:
            reasons.append("CrewAI execution is disabled")
        if self._crewai_enabled and self._crewai_disabled:
            reasons.append("CrewAI execution has been disabled after failures")
        return "; ".join(reasons) if reasons else "No model output available from any provider."
    @staticmethod
    def _normalize_crewai_model(model_name: str) -> str:
        normalized = (model_name or "").strip()
        if not normalized:
            return "groq/llama-3.3-70b-versatile"
        if "/" in normalized:
            return normalized
        return f"groq/{normalized}"

    @staticmethod
    def to_list(values: Any, default: list[str]) -> list[str]:
        if isinstance(values, list):
            cleaned = [str(item).strip() for item in values if str(item).strip()]
            if cleaned:
                return cleaned
        return default
