from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from langgraph.graph import END, START, StateGraph

from ..agents import AgentRegistry
from ..agents.resource_finder_agent import ResourceUnavailableError
from src.config.settings import Settings
from src.schemas.study_material import ArtifactIndex, ConceptContentPack, JobStatus, MaterialLifecycleStatus
from src.data.repositories import workflow_repository
from ..renderers.json_renderer import JsonRenderer
from ..renderers.pdf_renderer import PdfRenderer
from ..renderers.study_material_json_renderer import StudyMaterialJsonRenderer

logger = logging.getLogger("uvicorn.error")


class MaterialWorkflow:
    def __init__(
        self,
        settings: Settings,
        agents: AgentRegistry,
        pdf_renderer: PdfRenderer,
        json_renderer: JsonRenderer,
        study_material_json_renderer: StudyMaterialJsonRenderer,
    ) -> None:
        self.settings = settings
        self.agents = agents
        self.pdf_renderer = pdf_renderer
        self.json_renderer = json_renderer
        self.study_material_json_renderer = study_material_json_renderer
        self._graph = self._build_graph()

    async def run(self, job_id: str) -> dict[str, Any]:
        return await self._graph.ainvoke(
            {
                "job_id": job_id,
                "revision_cycle": 0,
                "max_revision_cycles": self.settings.max_revision_cycles,
            }
        )

    def _build_graph(self):
        graph = StateGraph(dict)

        graph.add_node("validate_request_node", self.validate_request_node)
        graph.add_node("load_subject_and_concepts_node", self.load_subject_and_concepts_node)
        graph.add_node("syllabus_interpreter_node", self.syllabus_interpreter_node)
        graph.add_node("student_pedagogy_node", self.student_pedagogy_node)
        graph.add_node("study_material_engine_node", self.study_material_engine_node)
        graph.add_node("concept_explainer_node", self.concept_explainer_node)
        graph.add_node("worked_example_node", self.worked_example_node)
        graph.add_node("practice_recall_node", self.practice_recall_node)
        graph.add_node("resource_finder_node", self.resource_finder_node)
        graph.add_node("quality_guardian_node", self.quality_guardian_node)
        graph.add_node("artifact_spec_node", self.artifact_spec_node)
        graph.add_node("artifact_render_node", self.artifact_render_node)
        graph.add_node("zip_bundle_node", self.zip_bundle_node)
        graph.add_node("persist_job_output_node", self.persist_job_output_node)
        graph.add_node("complete_or_fail_node", self.complete_or_fail_node)

        graph.add_edge(START, "validate_request_node")
        graph.add_edge("validate_request_node", "load_subject_and_concepts_node")
        graph.add_edge("load_subject_and_concepts_node", "syllabus_interpreter_node")
        graph.add_edge("syllabus_interpreter_node", "student_pedagogy_node")
        graph.add_edge("student_pedagogy_node", "study_material_engine_node")
        graph.add_edge("study_material_engine_node", "concept_explainer_node")
        graph.add_edge("concept_explainer_node", "worked_example_node")
        graph.add_edge("worked_example_node", "practice_recall_node")
        graph.add_edge("practice_recall_node", "resource_finder_node")
        graph.add_edge("resource_finder_node", "quality_guardian_node")
        graph.add_conditional_edges(
            "quality_guardian_node",
            self._quality_route,
            {
                "revise": "concept_explainer_node",
                "continue": "artifact_spec_node",
            },
        )
        graph.add_edge("artifact_spec_node", "artifact_render_node")
        graph.add_edge("artifact_render_node", "zip_bundle_node")
        graph.add_edge("zip_bundle_node", "persist_job_output_node")
        graph.add_edge("persist_job_output_node", "complete_or_fail_node")
        graph.add_edge("complete_or_fail_node", END)
        return graph.compile()

    async def validate_request_node(self, state: dict[str, Any]) -> dict[str, Any]:
        job = await workflow_repository.get_job(state["job_id"])
        subject = await workflow_repository.get_subject_record(job.subject_id)
        missing = [concept_id for concept_id in job.concept_ids if concept_id not in subject.concept_meta]
        if missing:
            raise ValueError(f"Missing concepts in subject: {missing}")
        concept_names = [subject.concept_meta[concept_id].name for concept_id in job.concept_ids]
        logger.info(
            "[MaterialJob:%s] Started generation for subject='%s' concepts=%s",
            job.job_id,
            subject.name,
            concept_names,
        )
        await self._update_job(job.job_id, status=JobStatus.running, progress=8)
        return {
            "job_id": state["job_id"],
            "subject_record": subject.model_dump(),
            "revision_cycle": state.get("revision_cycle", 0),
            "max_revision_cycles": state.get("max_revision_cycles", self.settings.max_revision_cycles),
        }

    async def load_subject_and_concepts_node(self, state: dict[str, Any]) -> dict[str, Any]:
        job = await workflow_repository.get_job(state["job_id"])
        subject = state["subject_record"]
        concept_states: dict[str, dict[str, Any]] = {}
        for concept_id in job.concept_ids:
            concept = subject["concept_meta"][concept_id]
            concept_states[concept_id] = {
                "concept_id": concept_id,
                "concept_name": concept["name"],
                "concept_description": concept.get("description"),
                "revision_feedback": job.revision_note,
            }
        await self._update_job(job.job_id, progress=12)
        return {
            "job_id": state["job_id"],
            "subject_record": subject,
            "concept_states": concept_states,
            "revision_cycle": state.get("revision_cycle", 0),
            "max_revision_cycles": state.get("max_revision_cycles", self.settings.max_revision_cycles),
        }

    async def syllabus_interpreter_node(self, state: dict[str, Any]) -> dict[str, Any]:
        subject = state["subject_record"]
        job = await workflow_repository.get_job(state["job_id"])
        concept_states = state["concept_states"]

        async def _run(item: dict[str, Any]) -> dict[str, Any]:
            await self._set_concept_status(job.job_id, item["concept_id"], "syllabus_mapping", item["concept_name"])
            coverage_map = await asyncio.to_thread(
                self.agents.syllabus_interpreter.execute,
                subject_name=subject["name"],
                grade_level=subject["grade_level"],
                concept_name=item["concept_name"],
                concept_description=item.get("concept_description"),
                learner_profile=job.learner_profile,
            )
            item["coverage_map"] = coverage_map
            return item

        updated = await self._map_concepts(concept_states, _run)
        await self._update_job(job.job_id, progress=22)
        return {
            "job_id": state["job_id"],
            "subject_record": subject,
            "concept_states": updated,
            "revision_cycle": state.get("revision_cycle", 0),
            "max_revision_cycles": state.get("max_revision_cycles", self.settings.max_revision_cycles),
        }

    async def student_pedagogy_node(self, state: dict[str, Any]) -> dict[str, Any]:
        subject = state["subject_record"]
        job = await workflow_repository.get_job(state["job_id"])
        concept_states = state["concept_states"]

        async def _run(item: dict[str, Any]) -> dict[str, Any]:
            await self._set_concept_status(job.job_id, item["concept_id"], "pedagogy_planning", item["concept_name"])
            item["teaching_plan"] = await asyncio.to_thread(
                self.agents.student_pedagogy.execute,
                concept_name=item["concept_name"],
                grade_level=subject["grade_level"],
                coverage_map=item.get("coverage_map", {}),
                learner_profile=job.learner_profile,
            )
            return item

        updated = await self._map_concepts(concept_states, _run)
        await self._update_job(job.job_id, progress=34)
        return {
            "job_id": state["job_id"],
            "subject_record": subject,
            "concept_states": updated,
            "revision_cycle": state.get("revision_cycle", 0),
            "max_revision_cycles": state.get("max_revision_cycles", self.settings.max_revision_cycles),
        }

    async def study_material_engine_node(self, state: dict[str, Any]) -> dict[str, Any]:
        subject = state["subject_record"]
        job = await workflow_repository.get_job(state["job_id"])
        concept_states = state["concept_states"]
        auto_revision_enabled = self.settings.max_revision_cycles > 0

        async def _run(item: dict[str, Any]) -> dict[str, Any]:
            await self._set_concept_status(
                job.job_id,
                item["concept_id"],
                "study_material_engine_generation",
                item["concept_name"],
            )
            try:
                item["engine_output"] = await asyncio.to_thread(
                    self.agents.study_material_engine.execute,
                    subject_name=subject["name"],
                    concept_name=item["concept_name"],
                    level=subject["grade_level"],
                    auto_revision_enabled=auto_revision_enabled,
                )
            except Exception as exc:
                item["engine_output_error"] = str(exc)
                logger.warning(
                    "[MaterialJob:%s] Study material engine failed for concept '%s': %s",
                    job.job_id,
                    item.get("concept_name", item["concept_id"]),
                    exc,
                )
            return item

        updated = await self._map_concepts(concept_states, _run)
        await self._update_job(job.job_id, progress=40)
        return {
            "job_id": state["job_id"],
            "subject_record": subject,
            "concept_states": updated,
            "revision_cycle": state.get("revision_cycle", 0),
            "max_revision_cycles": state.get("max_revision_cycles", self.settings.max_revision_cycles),
        }

    async def concept_explainer_node(self, state: dict[str, Any]) -> dict[str, Any]:
        subject = state["subject_record"]
        job = await workflow_repository.get_job(state["job_id"])
        concept_states = state["concept_states"]

        async def _run(item: dict[str, Any]) -> dict[str, Any]:
            await self._set_concept_status(job.job_id, item["concept_id"], "concept_explaining", item["concept_name"])
            item["core_notes"] = await asyncio.to_thread(
                self.agents.concept_explainer.execute,
                concept_name=item["concept_name"],
                grade_level=subject["grade_level"],
                coverage_map=item.get("coverage_map", {}),
                teaching_plan=item.get("teaching_plan", {}),
                revision_feedback=item.get("revision_feedback"),
            )
            return item

        updated = await self._map_concepts(concept_states, _run)
        await self._update_job(job.job_id, progress=45)
        return {
            "job_id": state["job_id"],
            "subject_record": subject,
            "concept_states": updated,
            "revision_cycle": state.get("revision_cycle", 0),
            "max_revision_cycles": state.get("max_revision_cycles", self.settings.max_revision_cycles),
        }

    async def worked_example_node(self, state: dict[str, Any]) -> dict[str, Any]:
        job = await workflow_repository.get_job(state["job_id"])
        concept_states = state["concept_states"]

        async def _run(item: dict[str, Any]) -> dict[str, Any]:
            await self._set_concept_status(job.job_id, item["concept_id"], "example_generation", item["concept_name"])
            core = item.get("core_notes", {})
            item["examples_pack"] = await asyncio.to_thread(
                self.agents.worked_example.execute,
                concept_name=item["concept_name"],
                key_steps=core.get("key_steps", []),
                revision_feedback=item.get("revision_feedback"),
                practical_examples_required=bool(core.get("practical_examples_required", True)),
            )
            return item

        updated = await self._map_concepts(concept_states, _run)
        await self._update_job(job.job_id, progress=55)
        return {
            "job_id": state["job_id"],
            "subject_record": state["subject_record"],
            "concept_states": updated,
            "revision_cycle": state.get("revision_cycle", 0),
            "max_revision_cycles": state.get("max_revision_cycles", self.settings.max_revision_cycles),
        }

    async def practice_recall_node(self, state: dict[str, Any]) -> dict[str, Any]:
        job = await workflow_repository.get_job(state["job_id"])
        concept_states = state["concept_states"]

        async def _run(item: dict[str, Any]) -> dict[str, Any]:
            await self._set_concept_status(job.job_id, item["concept_id"], "practice_generation", item["concept_name"])
            core = item.get("core_notes", {})
            examples = item.get("examples_pack", {}).get("examples", [])
            item["practice_pack"] = await asyncio.to_thread(
                self.agents.practice_recall.execute,
                concept_name=item["concept_name"],
                definition=core.get("definition", ""),
                examples=examples,
                revision_feedback=item.get("revision_feedback"),
            )
            return item

        updated = await self._map_concepts(concept_states, _run)
        await self._update_job(job.job_id, progress=64)
        return {
            "job_id": state["job_id"],
            "subject_record": state["subject_record"],
            "concept_states": updated,
            "revision_cycle": state.get("revision_cycle", 0),
            "max_revision_cycles": state.get("max_revision_cycles", self.settings.max_revision_cycles),
        }

    async def resource_finder_node(self, state: dict[str, Any]) -> dict[str, Any]:
        subject = state["subject_record"]
        job = await workflow_repository.get_job(state["job_id"])
        concept_states = state["concept_states"]

        async def _run(item: dict[str, Any]) -> dict[str, Any]:
            await self._set_concept_status(job.job_id, item["concept_id"], "resource_curation", item["concept_name"])
            try:
                item["resource_pack"] = await self.agents.resource_finder.execute(
                    subject_name=subject["name"],
                    grade_level=subject["grade_level"],
                    concept_name=item["concept_name"],
                )
                item["resource_required"] = True
                return item
            except ResourceUnavailableError as exc:
                await self._set_concept_status(
                    job.job_id,
                    item["concept_id"],
                    "resource_unavailable_skipped",
                    item["concept_name"],
                )
                item["skip_reason"] = str(exc)
                item["skip"] = True
                item["resource_required"] = False
                logger.warning(
                    "[MaterialJob:%s] Skipping concept '%s' (%s) due to missing resources.",
                    job.job_id,
                    item["concept_name"],
                    item["concept_id"],
                )
                return item

        updated = await self._map_concepts(concept_states, _run)
        kept = {cid: data for cid, data in updated.items() if not data.get("skip")}
        if not kept:
            if self.settings.allow_resourceless_generation:
                logger.warning(
                    "[MaterialJob:%s] No external resources found for any concept; continuing without resources.",
                    job.job_id,
                )
                for concept_id, data in updated.items():
                    data["skip"] = False
                    data["resource_required"] = False
                    data["resource_pack"] = {"references": []}
                    await self._set_concept_status(
                        job.job_id,
                        concept_id,
                        "resource_unavailable_continued",
                        data.get("concept_name", concept_id),
                    )
                kept = updated
            else:
                raise RuntimeError(
                    "All concepts were skipped due to missing external resources. "
                    "Generation cannot continue."
                )
        await self._update_job(job.job_id, progress=72)
        return {
            "job_id": state["job_id"],
            "subject_record": subject,
            "concept_states": kept,
            "revision_cycle": state.get("revision_cycle", 0),
            "max_revision_cycles": state.get("max_revision_cycles", self.settings.max_revision_cycles),
        }

    async def quality_guardian_node(self, state: dict[str, Any]) -> dict[str, Any]:
        job = await workflow_repository.get_job(state["job_id"])
        concept_states = state["concept_states"]
        revision_targets: dict[str, str] = {}

        async def _run(item: dict[str, Any]) -> dict[str, Any]:
            await self._set_concept_status(job.job_id, item["concept_id"], "quality_review", item["concept_name"])
            core = item.get("core_notes", {})
            draft = {
                **core,
                **item.get("examples_pack", {}),
                **item.get("practice_pack", {}),
                **item.get("resource_pack", {}),
            }
            quality_report = await asyncio.to_thread(
                self.agents.quality_guardian.execute,
                concept_name=item["concept_name"],
                content=draft,
                resource_required=item.get("resource_required", True),
            )
            item["quality_report"] = quality_report
            if not quality_report.get("approved", False):
                feedback = "; ".join(
                    [
                        *quality_report.get("issues", []),
                        *quality_report.get("guidance", []),
                    ]
                ).strip()
                if feedback:
                    revision_targets[item["concept_id"]] = feedback
                    item["revision_feedback"] = feedback
            return item

        updated = await self._map_concepts(concept_states, _run)
        revision_cycle = int(state.get("revision_cycle", 0))
        max_cycles = int(state.get("max_revision_cycles", 2))

        if revision_targets and revision_cycle < max_cycles:
            await self._update_job(job.job_id, progress=min(78, job.progress + 4))
            return {
                "job_id": state["job_id"],
                "subject_record": state["subject_record"],
                "concept_states": updated,
                "needs_revision": True,
                "revision_cycle": revision_cycle + 1,
                "max_revision_cycles": max_cycles,
            }

        await self._update_job(job.job_id, progress=80)
        return {
            "job_id": state["job_id"],
            "subject_record": state["subject_record"],
            "concept_states": updated,
            "needs_revision": False,
            "revision_cycle": revision_cycle,
            "max_revision_cycles": max_cycles,
        }

    async def artifact_spec_node(self, state: dict[str, Any]) -> dict[str, Any]:
        job = await workflow_repository.get_job(state["job_id"])
        concept_states = state["concept_states"]
        packs: list[dict[str, Any]] = []

        async def _run(item: dict[str, Any]) -> ConceptContentPack:
            await self._set_concept_status(job.job_id, item["concept_id"], "artifact_structuring", item["concept_name"])
            core = item.get("core_notes", {})
            content = {
                **core,
                **item.get("examples_pack", {}),
                **item.get("practice_pack", {}),
                **item.get("resource_pack", {}),
            }
            return await asyncio.to_thread(
                self.agents.artifact_spec.execute,
                concept_id=item["concept_id"],
                concept_name=item["concept_name"],
                content=content,
                resource_required=item.get("resource_required", True),
            )

        semaphore = asyncio.Semaphore(self.settings.max_parallel_concepts)
        tasks = []
        for concept_state in concept_states.values():
            tasks.append(self._run_with_semaphore(semaphore, _run(concept_state)))
        results = await asyncio.gather(*tasks)
        for pack in results:
            packs.append(pack.model_dump())

        await self._update_job(job.job_id, progress=86)
        return {
            "job_id": state["job_id"],
            "subject_record": state["subject_record"],
            "concept_states": concept_states,
            "concept_packs": packs,
            "revision_cycle": state.get("revision_cycle", 0),
            "max_revision_cycles": state.get("max_revision_cycles", self.settings.max_revision_cycles),
        }

    async def artifact_render_node(self, state: dict[str, Any]) -> dict[str, Any]:
        job = await workflow_repository.get_job(state["job_id"])
        subject = state["subject_record"]
        concept_packs = [ConceptContentPack(**pack) for pack in state.get("concept_packs", [])]

        output_dir = self.settings.material_output_dir / job.job_id
        output_dir.mkdir(parents=True, exist_ok=True)

        # Aggregate artifacts for admin review bundle.
        pdf_path = self.pdf_renderer.render(
            output_dir=output_dir,
            subject_name=subject["name"],
            grade_level=subject["grade_level"],
            concept_packs=concept_packs,
        )
        quick_pdf_path = self.pdf_renderer.render_quick_revision(
            output_dir=output_dir,
            subject_name=subject["name"],
            grade_level=subject["grade_level"],
            concept_packs=concept_packs,
        )
        json_paths = self.json_renderer.render(output_dir=output_dir, concept_packs=concept_packs)
        concept_states = state.get("concept_states", {})
        engine_payloads: list[dict[str, Any]] = []

        concept_artifacts: dict[str, dict[str, str]] = {}
        concepts_root = output_dir / "concepts"
        concepts_root.mkdir(parents=True, exist_ok=True)
        for pack in concept_packs:
            concept_dir = concepts_root / pack.concept_id
            concept_dir.mkdir(parents=True, exist_ok=True)
            c_pdf = self.pdf_renderer.render(
                output_dir=concept_dir,
                subject_name=subject["name"],
                grade_level=subject["grade_level"],
                concept_packs=[pack],
            )
            c_quick_pdf = self.pdf_renderer.render_quick_revision(
                output_dir=concept_dir,
                subject_name=subject["name"],
                grade_level=subject["grade_level"],
                concept_packs=[pack],
            )
            c_json = self.json_renderer.render(output_dir=concept_dir, concept_packs=[pack])
            concept_artifacts[pack.concept_id] = {
                "pdf": str(c_pdf),
                "quick_revision_pdf": str(c_quick_pdf),
                **{name: str(path) for name, path in c_json.items()},
            }
            concept_state = concept_states.get(pack.concept_id, {})
            engine_output = concept_state.get("engine_output")
            if engine_output:
                engine_payloads.append(
                    {
                        "concept_id": pack.concept_id,
                        "concept_name": pack.concept_name,
                        "study_material": engine_output,
                    }
                )
                c_engine_json = self.study_material_json_renderer.render_concept(
                    output_dir=concept_dir,
                    payload=engine_output,
                )
                concept_artifacts[pack.concept_id]["study_material_json"] = str(c_engine_json)

        engine_json_path = None
        if engine_payloads:
            engine_json_path = self.study_material_json_renderer.render(
                output_dir=output_dir,
                subject_name=subject["name"],
                grade_level=subject["grade_level"],
                concept_payloads=engine_payloads,
            )

        await self._update_job(job.job_id, progress=93)
        artifacts = {
            "pdf": str(pdf_path),
            "quick_revision_pdf": str(quick_pdf_path),
            **{name: str(path) for name, path in json_paths.items()},
        }
        if engine_json_path:
            artifacts["study_material_json"] = str(engine_json_path)
        return {
            "job_id": state["job_id"],
            "subject_record": subject,
            "concept_states": concept_states,
            "concept_packs": state.get("concept_packs", []),
            "output_dir": str(output_dir),
            "artifacts": artifacts,
            "concept_artifacts": concept_artifacts,
        }

    async def zip_bundle_node(self, state: dict[str, Any]) -> dict[str, Any]:
        output_dir = Path(state["output_dir"])
        zip_path = output_dir / "study_material_bundle.zip"
        with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as zf:
            for file_path in output_dir.rglob("*"):
                if file_path.is_file() and file_path.name != zip_path.name:
                    zf.write(file_path, arcname=str(file_path.relative_to(output_dir)))

        artifacts = dict(state.get("artifacts", {}))
        artifacts["zip"] = str(zip_path)

        concept_artifacts = dict(state.get("concept_artifacts", {}))
        for concept_id, artifact_map in concept_artifacts.items():
            concept_dir = output_dir / "concepts" / concept_id
            concept_zip = concept_dir / "study_material_bundle.zip"
            with ZipFile(concept_zip, "w", compression=ZIP_DEFLATED) as zf:
                for file_path in concept_dir.iterdir():
                    if file_path.is_file() and file_path.name != concept_zip.name:
                        zf.write(file_path, arcname=file_path.name)
            artifact_map["zip"] = str(concept_zip)
        return {
            "job_id": state["job_id"],
            "subject_record": state["subject_record"],
            "concept_states": state.get("concept_states", {}),
            "concept_packs": state.get("concept_packs", []),
            "output_dir": str(output_dir),
            "artifacts": artifacts,
            "concept_artifacts": concept_artifacts,
        }

    async def persist_job_output_node(self, state: dict[str, Any]) -> dict[str, Any]:
        job = await workflow_repository.get_job(state["job_id"])
        artifacts = state.get("artifacts", {})
        concept_artifacts = state.get("concept_artifacts", {})
        concept_states = state.get("concept_states", {})
        concept_name_by_id = {
            concept_id: concept_data.get("concept_name", concept_id)
            for concept_id, concept_data in concept_states.items()
            if isinstance(concept_data, dict)
        }

        def _to_filename(value: str | None) -> str | None:
            if not value:
                return None
            return Path(value).name

        job.artifact_index = ArtifactIndex(
            pdf=_to_filename(artifacts.get("pdf")),
            quick_revision_pdf=_to_filename(artifacts.get("quick_revision_pdf")),
            quiz_json=_to_filename(artifacts.get("quiz_json")),
            flashcards_json=_to_filename(artifacts.get("flashcards_json")),
            resources_json=_to_filename(artifacts.get("resources_json")),
            study_material_json=_to_filename(artifacts.get("study_material_json")),
            zip=_to_filename(artifacts.get("zip")),
        )
        job.concept_artifacts = {
            concept_id: ArtifactIndex(
                pdf=_to_filename(artifact_map.get("pdf")),
                quick_revision_pdf=_to_filename(artifact_map.get("quick_revision_pdf")),
                quiz_json=_to_filename(artifact_map.get("quiz_json")),
                flashcards_json=_to_filename(artifact_map.get("flashcards_json")),
                resources_json=_to_filename(artifact_map.get("resources_json")),
                study_material_json=_to_filename(artifact_map.get("study_material_json")),
                zip=_to_filename(artifact_map.get("zip")),
            )
            for concept_id, artifact_map in concept_artifacts.items()
        }
        output_dir = state.get("output_dir")
        job.output_dir = Path(output_dir).name if output_dir else None
        job.progress = 98
        for concept_id in concept_states.keys():
            concept_name = concept_name_by_id.get(concept_id, concept_id)
            job.concept_statuses[concept_id] = "generated_ready_for_review"
            logger.info(
                "[MaterialJob:%s] Concept generated successfully: '%s' (%s)",
                job.job_id,
                concept_name,
                concept_id,
            )
        await workflow_repository.update_job(job)
        return {
            "job_id": state["job_id"],
            "subject_record": state["subject_record"],
            "concept_states": state.get("concept_states", {}),
            "concept_packs": state.get("concept_packs", []),
            "output_dir": state.get("output_dir"),
            "artifacts": state.get("artifacts", {}),
            "concept_artifacts": state.get("concept_artifacts", {}),
        }

    async def complete_or_fail_node(self, state: dict[str, Any]) -> dict[str, Any]:
        job = await workflow_repository.get_job(state["job_id"])
        if job.errors:
            job.status = JobStatus.failed
            job.progress = min(job.progress, 99)
            logger.error("[MaterialJob:%s] Failed. Errors=%s", job.job_id, job.errors)
        else:
            job.status = JobStatus.completed
            job.progress = 100
            logger.info("[MaterialJob:%s] Completed successfully.", job.job_id)
        await workflow_repository.update_job_fields(job)
        return {
            "job_id": state["job_id"],
            "final_status": job.status.value,
        }

    @staticmethod
    def _quality_route(state: dict[str, Any]) -> str:
        if state.get("needs_revision"):
            return "revise"
        return "continue"

    async def _map_concepts(
        self,
        concept_states: dict[str, dict[str, Any]],
        task_callback,
    ) -> dict[str, dict[str, Any]]:
        semaphore = asyncio.Semaphore(self.settings.max_parallel_concepts)
        tasks = [self._run_with_semaphore(semaphore, self._run_concept_task(task_callback, concept)) for concept in concept_states.values()]
        results = await asyncio.gather(*tasks)
        return {result["concept_id"]: result for result in results}

    @staticmethod
    async def _run_with_semaphore(semaphore: asyncio.Semaphore, coroutine):
        async with semaphore:
            return await coroutine

    async def _run_concept_task(self, task_callback, concept: dict[str, Any]) -> dict[str, Any]:
        attempts = max(self.settings.agent_retry_attempts, 1)
        last_exc: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                concept_copy = dict(concept)
                node_timeout = max(self.settings.request_timeout_seconds * 2, 20)
                return await asyncio.wait_for(task_callback(concept_copy), timeout=node_timeout)
            except Exception as exc:
                last_exc = exc
                if attempt < attempts:
                    await asyncio.sleep(min(2**(attempt - 1), 4))
        raise RuntimeError(f"Concept pipeline failed for '{concept.get('concept_name')}'. {last_exc}")

    async def _update_job(self, job_id: str, status: JobStatus | None = None, progress: int | None = None) -> None:
        job = await workflow_repository.get_job(job_id)
        if status:
            job.status = status
        if progress is not None:
            job.progress = progress
        await workflow_repository.update_job_fields(job)

    async def _set_concept_status(self, job_id: str, concept_id: str, status_text: str, concept_name: str | None = None) -> None:
        job = await workflow_repository.get_job(job_id)
        previous = job.concept_statuses.get(concept_id)
        await workflow_repository.set_concept_status(job_id, concept_id, status_text)
        if previous != status_text:
            logger.info(
                "[MaterialJob:%s] Concept status: '%s' (%s) -> %s",
                job_id,
                concept_name or concept_id,
                concept_id,
                status_text,
            )
