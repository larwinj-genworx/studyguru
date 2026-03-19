from __future__ import annotations

import unittest

from src.config.settings import Settings
from src.core.services import material_job_service
from src.core.services.object_storage_service import ObjectStorageService
from src.schemas.study_material import ArtifactIndex, JobRecord, JobStatus, ReviewStatus


def build_settings(**overrides) -> Settings:
    return Settings(JWT_SECRET="x" * 16, **overrides)


class ObjectStorageServiceTests(unittest.TestCase):
    def test_object_name_preserves_material_folder_structure(self) -> None:
        service = ObjectStorageService(build_settings())
        object_name = service._object_name(service.material_area, "job-123/concepts/c1/flashcards.json")
        self.assertEqual(
            object_name,
            "studyguru/study_material/job-123/concepts/c1/flashcards.json",
        )

    def test_normalize_relative_path_rejects_traversal(self) -> None:
        with self.assertRaises(ValueError):
            ObjectStorageService._normalize_relative_path("../secret.txt")


class MaterialJobServicePathTests(unittest.TestCase):
    def test_resolve_concept_artifact_relative_path(self) -> None:
        record = JobRecord(
            job_id="job-123",
            subject_id="subject-1",
            concept_ids=["concept-1"],
            status=JobStatus.completed,
            review_status=ReviewStatus.pending_review,
            output_dir="job-123",
            concept_artifacts={
                "concept-1": ArtifactIndex(flashcards_json="flashcards.json"),
            },
        )

        relative_path = material_job_service.resolve_concept_artifact_relative_path(
            record,
            "concept-1",
            "flashcards_json",
        )

        self.assertEqual(
            relative_path,
            "job-123/concepts/concept-1/flashcards.json",
        )


if __name__ == "__main__":
    unittest.main()
