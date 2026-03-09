from __future__ import annotations

import asyncio
import logging
import re
from collections import Counter
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from src.config.settings import Settings
from src.control.study_material_generation.retrieval.models import SearchResult, extract_domain
from src.control.study_material_generation.retrieval.service import EvidenceRetrievalService
from src.schemas.study_material import LearningContent

from ..models import PageImageCandidate, VisualQueryPlan


logger = logging.getLogger("uvicorn.error")

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class ConceptImageRetrievalService:
    _STOPWORDS = {
        "about",
        "after",
        "also",
        "and",
        "are",
        "chapter",
        "class",
        "concept",
        "content",
        "exam",
        "explained",
        "for",
        "formula",
        "free",
        "from",
        "grade",
        "guide",
        "important",
        "introduction",
        "lesson",
        "math",
        "mathematics",
        "material",
        "materials",
        "notes",
        "overview",
        "pdf",
        "question",
        "questions",
        "revision",
        "science",
        "simple",
        "solution",
        "solutions",
        "study",
        "subject",
        "summary",
        "textbook",
        "the",
        "their",
        "these",
        "this",
        "topic",
        "using",
        "what",
        "with",
    }
    _IMAGE_POSITIVE_KEYWORDS = {
        "diagram",
        "labeled",
        "illustration",
        "figure",
        "graph",
        "chart",
        "structure",
        "process",
        "geometry",
        "net",
        "cell",
        "reaction",
        "flow",
        "model",
    }
    _COMMERCIAL_TOKENS = {
        "apparel",
        "bag",
        "bottle",
        "bookset",
        "buy",
        "challenge",
        "coffee",
        "combo",
        "course",
        "courses",
        "hoodie",
        "hooded",
        "merch",
        "merchandise",
        "mug",
        "neck",
        "notebook",
        "offer",
        "pen",
        "pricing",
        "round",
        "sale",
        "shirt",
        "shopping",
        "shop",
        "sweatshirt",
        "tshirt",
        "t-shirt",
        "womens",
        "women",
        "mens",
        "men",
    }
    _GENERIC_IMAGE_LABELS = {
        "tp imag",
        "tp-imag",
        "ff image",
        "ffimage",
        "ck12 foundation",
    }
    _TRUSTED_IMAGE_CDN_ROOTS = {
        "britannica.com",
        "ck12.org",
        "libretexts.org",
        "mathsisfun.com",
        "openstax.org",
    }
    _IMAGE_NEGATIVE_TOKENS = {
        "logo",
        "icon",
        "avatar",
        "profile",
        "banner",
        "ad",
        "advertisement",
        "sprite",
        "emoji",
        "thumbnail",
        "placeholder",
        "watermark",
        "stock",
        "shutterstock",
        "getty",
        "istock",
        "alamy",
        "arrow",
        "toggle",
        "download",
        "widget",
        "store",
        "navbar",
        "header",
        "footer",
        "symbol",
        "lcpimage",
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.evidence = EvidenceRetrievalService(settings)
        self._headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }

    async def discover_candidates(
        self,
        *,
        subject_name: str,
        grade_level: str,
        concept_name: str,
        concept_description: str | None,
        content: LearningContent,
    ) -> list[PageImageCandidate]:
        concept_tokens = self._build_concept_tokens(
            subject_name=subject_name,
            concept_name=concept_name,
            concept_description=concept_description,
            content=content,
        )
        plans = self._build_visual_plans(
            subject_name=subject_name,
            grade_level=grade_level,
            concept_name=concept_name,
            concept_description=concept_description,
            content=content,
        )
        search_queries = self._build_search_queries(
            subject_name=subject_name,
            grade_level=grade_level,
            concept_name=concept_name,
            concept_description=concept_description,
            plans=plans,
        )
        search_results = await self.evidence._search_queries(
            search_queries,
            max_results_per_query=max(self.settings.concept_image_max_pages, 3),
        )
        ranked_results = sorted(
            (
                (result, self._score_search_result(result=result, concept_tokens=concept_tokens, concept_name=concept_name))
                for result in search_results
            ),
            key=lambda item: item[1],
            reverse=True,
        )
        selected_pages = [
            result
            for result, score in ranked_results
            if score >= 0.35
        ][: max(self.settings.concept_image_max_pages, 1)]
        logger.info(
            "[ConceptImageRetrieval] Candidate page discovery completed for concept='%s'. plans=%d pages=%d",
            concept_name,
            len(plans),
            len(selected_pages),
        )
        for page_result in selected_pages:
            logger.info(
                "[ConceptImageRetrieval] Selected concept page for concept='%s'. title=%s url=%s",
                concept_name,
                page_result.title,
                page_result.url,
            )

        candidates: list[PageImageCandidate] = []
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(max(self.settings.resource_search_timeout_seconds, 8)),
            headers=self._headers,
            follow_redirects=True,
        ) as client:
            semaphore = asyncio.Semaphore(3)

            async def _process_page(page_result: SearchResult) -> list[PageImageCandidate]:
                async with semaphore:
                    return await self._extract_page_candidates(
                        client,
                        page_result,
                        plans,
                        concept_tokens,
                        concept_name=concept_name,
                    )

            results = await asyncio.gather(*[_process_page(result) for result in selected_pages], return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                continue
            candidates.extend(result)

        deduped: list[PageImageCandidate] = []
        seen_urls: set[str] = set()
        for candidate in sorted(candidates, key=lambda item: item.relevance_score, reverse=True):
            canonical = candidate.source_image_url.strip()
            if not canonical or canonical in seen_urls:
                continue
            seen_urls.add(canonical)
            deduped.append(candidate)
            if len(deduped) >= max(self.settings.concept_image_max_candidates * 3, 12):
                break
        for candidate in deduped:
            logger.info(
                "[ConceptImageRetrieval] Candidate image selected for concept='%s'. score=%.4f page=%s image=%s",
                concept_name,
                candidate.relevance_score,
                candidate.source_page_url,
                candidate.source_image_url,
            )
        return deduped

    def _build_search_queries(
        self,
        *,
        subject_name: str,
        grade_level: str,
        concept_name: str,
        concept_description: str | None,
        plans: list[VisualQueryPlan],
    ) -> list[str]:
        queries = [
            f"{grade_level} {subject_name} {concept_name} {plan.search_hint}"
            for plan in plans
        ]
        queries.append(f"{concept_name} labeled diagram {subject_name}")
        if concept_description:
            queries.append(f"{concept_name} {concept_description[:60]} diagram")
        deduped: list[str] = []
        seen: set[str] = set()
        for query in queries:
            cleaned = " ".join(query.split()).strip()
            key = cleaned.lower()
            if not cleaned or key in seen:
                continue
            seen.add(key)
            deduped.append(cleaned)
        return deduped[: max(len(plans) + 1, 3)]

    def _build_concept_tokens(
        self,
        *,
        subject_name: str,
        concept_name: str,
        concept_description: str | None,
        content: LearningContent,
    ) -> set[str]:
        text_segments = [subject_name, concept_name, concept_description or "", *content.highlights[:8]]
        for section in content.sections[:8]:
            text_segments.append(section.title)
            text_segments.extend(self._extract_section_strings(section, depth=0))
        concept_seed_tokens = {
            token
            for token in _TOKEN_RE.findall(f"{concept_name} {concept_description or ''}".lower())
            if len(token) > 2 and token not in self._STOPWORDS
        }
        counts = Counter(
            token
            for token in _TOKEN_RE.findall(" ".join(text_segments).lower())
            if len(token) > 2 and token not in self._STOPWORDS
        )
        return {
            token
            for token, count in counts.items()
            if token in concept_seed_tokens
            or count >= 2
            or self._contains_structural_learning_signal(token)
        }

    def _extract_section_strings(self, section, depth: int) -> list[str]:
        if depth > 2:
            return []
        collected: list[str] = []
        for block in section.blocks[:10]:
            collected.extend(self._extract_block_strings(block))
        for child in section.children[:5]:
            collected.append(child.title)
            collected.extend(self._extract_section_strings(child, depth + 1))
        return collected

    def _extract_block_strings(self, block: dict) -> list[str]:
        collected: list[str] = []
        block_type = str(block.get("type", "")).lower()

        def add_text(value: str | None) -> None:
            if not isinstance(value, str):
                return
            cleaned = " ".join(value.split()).strip()
            if not cleaned:
                return
            words = cleaned.split()
            if len(words) > 18 and not self._contains_structural_learning_signal(cleaned):
                return
            collected.append(cleaned)

        if block_type == "paragraph":
            add_text(block.get("text"))
            return collected
        if block_type == "callout":
            add_text(block.get("title"))
            for item in block.get("content", [])[:6]:
                add_text(item)
            return collected
        if block_type == "list":
            for item in block.get("items", [])[:8]:
                add_text(item)
            return collected
        if block_type == "formula":
            add_text(block.get("title"))
            add_text(block.get("expression"))
            add_text(block.get("explanation"))
            return collected
        if block_type == "example":
            add_text(block.get("title"))
            return collected

        for key in ("title", "text", "label", "expression"):
            add_text(block.get(key))
        return collected

    def _score_search_result(
        self,
        *,
        result: SearchResult,
        concept_tokens: set[str],
        concept_name: str,
    ) -> float:
        text = " ".join((result.title, result.snippet, result.url)).lower()
        tokens = set(_TOKEN_RE.findall(text))
        overlap = len(tokens & concept_tokens) / max(len(concept_tokens), 1)
        concept_phrase = concept_name.lower().strip()
        phrase_match = 1.0 if concept_phrase and concept_phrase in text else 0.0
        strong_overlap = 1.0 if self._has_minimum_overlap(tokens, concept_tokens, minimum=2) else 0.0
        commercial_penalty = 0.3 if tokens & self._COMMERCIAL_TOKENS else 0.0
        return max(
            0.0,
            (phrase_match * 0.52) + (overlap * 0.28) + (strong_overlap * 0.1) + (result.domain_score * 0.1) - commercial_penalty,
        )

    def _build_visual_plans(
        self,
        *,
        subject_name: str,
        grade_level: str,
        concept_name: str,
        concept_description: str | None,
        content: LearningContent,
    ) -> list[VisualQueryPlan]:
        base_text = " ".join(
            [
                subject_name,
                grade_level,
                concept_name,
                concept_description or "",
                *content.highlights[:4],
                *[section.title for section in content.sections[:6]],
            ]
        ).lower()
        plans: list[VisualQueryPlan] = [
            VisualQueryPlan(
                label="Concept Diagram",
                search_hint="labeled diagram educational figure",
                caption_hint=f"Visual diagram for {concept_name}",
            ),
            VisualQueryPlan(
                label="Concept Illustration",
                search_hint="illustration concept explanation visual",
                caption_hint=f"Illustrated explanation of {concept_name}",
            ),
        ]
        if any(token in base_text for token in ("graph", "kinetics", "rate", "trend", "curve")):
            plans.append(
                VisualQueryPlan(
                    label="Graph Representation",
                    search_hint="graph chart labeled figure",
                    caption_hint=f"Graph-based view of {concept_name}",
                )
            )
        elif any(token in base_text for token in ("trigonometric", "trigonometry", "sine", "cosine", "tangent", "ratio", "identity")):
            plans.append(
                VisualQueryPlan(
                    label="Trigonometry Representation",
                    search_hint="right triangle unit circle sine cosine tangent labeled diagram",
                    caption_hint=f"Trigonometry visual for {concept_name}",
                )
            )
        elif any(token in base_text for token in ("surface area", "volume", "solid", "shape", "triangle", "geometry", "mensuration", "net")):
            plans.append(
                VisualQueryPlan(
                    label="Geometry Representation",
                    search_hint="geometry labeled figure net 3d shape",
                    caption_hint=f"Geometry-focused visual for {concept_name}",
                )
            )
        elif any(token in base_text for token in ("cell", "electrode", "reaction", "structure", "process", "cycle")):
            plans.append(
                VisualQueryPlan(
                    label="Process or Structure",
                    search_hint="labeled structure process diagram",
                    caption_hint=f"Process or structure view of {concept_name}",
                )
            )
        deduped: list[VisualQueryPlan] = []
        seen: set[str] = set()
        for plan in plans:
            key = plan.search_hint.lower().strip()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(plan)
        return deduped[:3]

    async def _extract_page_candidates(
        self,
        client: httpx.AsyncClient,
        page_result: SearchResult,
        plans: list[VisualQueryPlan],
        concept_tokens: set[str],
        *,
        concept_name: str,
    ) -> list[PageImageCandidate]:
        page_url = page_result.url
        lowered_url = page_url.lower()
        if lowered_url.endswith(".pdf") or "/pdf" in lowered_url:
            return []
        try:
            response = await client.get(page_url)
            if response.status_code >= 400:
                return []
            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type:
                return []
        except Exception:
            return []

        soup = BeautifulSoup(response.text, "lxml")
        container = soup.find("article") or soup.find("main") or soup.body
        if container is None:
            return []

        page_title = ""
        if soup.title and soup.title.string:
            page_title = soup.title.string.strip()
        heading_text = " ".join(
            node.get_text(" ", strip=True)
            for node in container.select("h1, h2, h3")[:4]
        ).strip()
        meta_description = ""
        meta_tag = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
        if meta_tag:
            meta_description = " ".join(str(meta_tag.get("content", "")).split()).strip()
        page_context = " ".join(part for part in (page_title, heading_text, meta_description, page_result.title, page_result.snippet) if part).strip()
        page_tokens = set(_TOKEN_RE.findall(page_context.lower()))
        page_overlap = len(page_tokens & concept_tokens) / max(len(concept_tokens), 1)
        if concept_name.lower().strip() not in page_context.lower() and page_overlap < 0.12:
            return []
        domain = extract_domain(page_url)
        images = container.select("figure img, img")
        candidates: list[PageImageCandidate] = []
        for img in images:
            src = self._resolve_img_src(img, page_url)
            if not src or self._reject_src(src):
                continue
            if self._reject_external_image_domain(page_url, src):
                continue
            alt_text = " ".join(str(img.get("alt", "")).split()).strip()
            title = " ".join(str(img.get("title", "")).split()).strip()
            caption = ""
            figure = img.find_parent("figure")
            if figure:
                figcaption = figure.find("figcaption")
                if figcaption:
                    caption = " ".join(figcaption.get_text(" ", strip=True).split()).strip()
            nearby_text = self._extract_nearby_text(figure or img)
            filename_text = self._extract_filename_tokens(src)
            local_text = " ".join(part for part in (alt_text, title, caption, nearby_text, filename_text) if part).strip()
            if self._reject_metadata(local_text, src):
                continue

            width_hint = self._safe_int(img.get("width"))
            height_hint = self._safe_int(img.get("height"))
            score = self._score_candidate(
                text=local_text,
                concept_tokens=concept_tokens,
                domain=domain,
                width_hint=width_hint,
                height_hint=height_hint,
                in_figure=figure is not None,
                page_overlap=page_overlap,
            )
            if score <= 0.22:
                continue
            plan = plans[0]
            local_text_lower = local_text.lower()
            if any(keyword in local_text_lower for keyword in ("graph", "curve", "chart")):
                plan = next((item for item in plans if "Graph" in item.label), plan)
            elif any(keyword in local_text_lower for keyword in ("shape", "triangle", "volume", "surface area", "solid")):
                plan = next((item for item in plans if "Geometry" in item.label), plan)
            elif any(keyword in local_text_lower for keyword in ("cell", "process", "reaction", "structure", "electrode", "bridge")):
                plan = next((item for item in plans if "Process" in item.label), plan)

            fallback_title = caption or alt_text or title or page_title or plan.caption_hint
            normalized_title = self._normalize_candidate_title(
                title=fallback_title,
                page_title=page_title,
                plan_caption=plan.caption_hint,
            )
            candidates.append(
                PageImageCandidate(
                    title=normalized_title[:220],
                    caption=(caption or plan.caption_hint)[:320],
                    alt_text=(alt_text or normalized_title)[:320],
                    intent_label=plan.label,
                    source_page_url=page_url,
                    source_image_url=src,
                    source_domain=domain,
                    relevance_score=round(score, 4),
                    width_hint=width_hint,
                    height_hint=height_hint,
                    mime_type_hint=None,
                )
            )
        if candidates:
            logger.info(
                "[ConceptImageRetrieval] Page image extraction completed. page=%s candidates=%d",
                page_url,
                len(candidates),
            )
        return candidates

    @staticmethod
    def _resolve_img_src(img, page_url: str) -> str | None:
        for key in ("src", "data-src", "data-original", "data-lazy-src"):
            value = str(img.get(key, "")).strip()
            if value:
                return urljoin(page_url, value)
        srcset = str(img.get("srcset", "")).strip()
        if srcset:
            first = srcset.split(",")[0].strip().split(" ")[0].strip()
            if first:
                return urljoin(page_url, first)
        return None

    def _score_candidate(
        self,
        *,
        text: str,
        concept_tokens: set[str],
        domain: str,
        width_hint: int | None,
        height_hint: int | None,
        in_figure: bool,
        page_overlap: float,
    ) -> float:
        tokens = set(_TOKEN_RE.findall(text.lower()))
        overlap = len(tokens & concept_tokens) / max(len(concept_tokens), 1)
        positive_hits = len(tokens & self._IMAGE_POSITIVE_KEYWORDS)
        if tokens & self._COMMERCIAL_TOKENS:
            return 0.0
        if overlap == 0 and page_overlap < 0.22 and positive_hits == 0:
            return 0.0
        trust_score = self.evidence._score_domain(domain)  # reuse retrieval trust scoring
        dimension_bonus = 0.0
        if width_hint and height_hint:
            if width_hint >= self.settings.concept_image_min_width and height_hint >= self.settings.concept_image_min_height:
                dimension_bonus = 0.1
        figure_bonus = 0.1 if in_figure else 0.0
        descriptor_bonus = 0.1 if len(tokens) >= 2 else 0.0
        return (
            (trust_score * 0.16)
            + (overlap * 0.34)
            + (page_overlap * 0.26)
            + (min(positive_hits, 3) * 0.06)
            + dimension_bonus
            + figure_bonus
            + descriptor_bonus
        )

    def _reject_src(self, src: str) -> bool:
        lowered = src.lower()
        if lowered.startswith("data:"):
            return True
        url_tokens = set(_TOKEN_RE.findall(lowered))
        if url_tokens & self._IMAGE_NEGATIVE_TOKENS:
            return True
        if url_tokens & self._COMMERCIAL_TOKENS:
            return True
        if lowered.endswith(".svg") or lowered.endswith(".gif"):
            return True
        parsed = urlparse(src)
        return parsed.scheme not in {"http", "https"}

    def _reject_metadata(self, text: str, src: str) -> bool:
        lowered = f"{text} {src}".lower()
        normalized_text = " ".join(text.lower().split())
        normalized_text = normalized_text.replace("_", " ").replace("-", " ")
        if normalized_text in self._GENERIC_IMAGE_LABELS:
            return True
        tokens = set(_TOKEN_RE.findall(lowered))
        if tokens & self._IMAGE_NEGATIVE_TOKENS:
            return True
        if tokens & self._COMMERCIAL_TOKENS:
            return True
        if len(tokens) < 2:
            return True
        return len(lowered.strip()) < 12

    def _reject_external_image_domain(self, page_url: str, image_url: str) -> bool:
        page_domain = extract_domain(page_url)
        image_domain = extract_domain(image_url)
        if not image_domain:
            return True
        page_root = self._root_domain(page_domain)
        image_root = self._root_domain(image_domain)
        if page_root and image_root and page_root == image_root:
            return False
        if image_root in self._TRUSTED_IMAGE_CDN_ROOTS:
            return False
        return True

    @staticmethod
    def _extract_filename_tokens(src: str) -> str:
        path = urlparse(src).path.rsplit("/", 1)[-1]
        return " ".join(_TOKEN_RE.findall(path.lower()))

    @staticmethod
    def _root_domain(domain: str) -> str:
        parts = [part for part in domain.lower().split(".") if part]
        if len(parts) >= 2:
            return ".".join(parts[-2:])
        return domain.lower()

    def _normalize_candidate_title(self, *, title: str, page_title: str, plan_caption: str) -> str:
        cleaned = " ".join(title.split()).strip()
        if not cleaned:
            return plan_caption
        if self._looks_like_placeholder_title(cleaned):
            if page_title:
                return page_title
            return plan_caption
        return cleaned

    @staticmethod
    def _looks_like_placeholder_title(value: str) -> bool:
        lowered = value.lower().strip()
        if lowered.endswith((".png", ".jpg", ".jpeg", ".webp")):
            return True
        tokens = _TOKEN_RE.findall(lowered)
        if not tokens:
            return True
        if len(tokens) == 1 and len(tokens[0]) >= 16:
            return True
        return False

    @staticmethod
    def _contains_structural_learning_signal(text: str) -> bool:
        lowered = text.lower()
        if "=" in text or "^" in text:
            return True
        signal_tokens = {
            "angle",
            "cell",
            "cos",
            "cosine",
            "equation",
            "formula",
            "identity",
            "ratio",
            "reaction",
            "sec",
            "sin",
            "sine",
            "tan",
            "tangent",
            "theta",
            "triangle",
            "unit circle",
        }
        return any(token in lowered for token in signal_tokens)

    @staticmethod
    def _extract_nearby_text(node) -> str:
        texts: list[str] = []
        current = node
        for _ in range(3):
            if current is None:
                break
            snippet = " ".join(current.get_text(" ", strip=True).split()).strip()
            if snippet:
                texts.append(snippet[:240])
            current = current.parent
        return " ".join(texts)

    @staticmethod
    def _has_minimum_overlap(tokens: set[str], query_tokens: set[str], minimum: int) -> bool:
        return len(tokens & query_tokens) >= minimum

    @staticmethod
    def _safe_int(value) -> int | None:
        try:
            parsed = int(str(value).strip())
            return parsed if parsed > 0 else None
        except Exception:
            return None
