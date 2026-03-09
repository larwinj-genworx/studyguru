from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from src.config.settings import Settings
from src.schemas.study_material import LearningContent

from ..models import PageImageCandidate
from ..retrieval import ConceptImageRetrievalService
from ..storage import ConceptImageStorageService, StoredConceptImage


logger = logging.getLogger("uvicorn.error")


@dataclass(slots=True)
class CuratedConceptImage:
    candidate: PageImageCandidate
    stored: StoredConceptImage


class ConceptImageCurationEngine:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.retrieval = ConceptImageRetrievalService(settings)
        self.storage = ConceptImageStorageService(settings)

    async def curate(
        self,
        *,
        subject_id: str,
        subject_name: str,
        grade_level: str,
        concept_name: str,
        concept_description: str | None,
        concept_material_id: str,
        content: LearningContent,
        existing_fingerprints: set[str],
    ) -> list[CuratedConceptImage]:
        candidates = await self.retrieval.discover_candidates(
            subject_name=subject_name,
            grade_level=grade_level,
            concept_name=concept_name,
            concept_description=concept_description,
            content=content,
        )
        curated: list[CuratedConceptImage] = []
        seen_fingerprints = set(existing_fingerprints)
        for index, candidate in enumerate(candidates, start=1):
            stable_key = f"{candidate.source_image_url}|{candidate.intent_label}|{candidate.source_page_url}"
            digest = hashlib.sha1(stable_key.encode("utf-8")).hexdigest()[:12]
            image_id = f"img{index:02d}-{digest}"
            stored = await self.storage.download_and_store(
                candidate=candidate,
                subject_id=subject_id,
                concept_material_id=concept_material_id,
                image_id=image_id,
            )
            if not stored:
                continue
            if self._is_duplicate(stored.fingerprint, seen_fingerprints):
                self.storage.remove_paths(stored.relative_image_path, stored.relative_thumbnail_path)
                continue
            seen_fingerprints.add(stored.fingerprint)
            logger.info(
                "[ConceptImageCuration] Curated image kept for concept='%s'. page=%s image=%s local=%s",
                concept_name,
                candidate.source_page_url,
                candidate.source_image_url,
                stored.relative_image_path,
            )
            curated.append(CuratedConceptImage(candidate=candidate, stored=stored))
            if len(curated) >= max(self.settings.concept_image_max_candidates, 1):
                break
        logger.info(
            "[ConceptImageCuration] Curated images completed for concept='%s'. candidates=%d kept=%d",
            concept_name,
            len(candidates),
            len(curated),
        )
        return curated

    @staticmethod
    def _is_duplicate(candidate_fingerprint: str, existing_fingerprints: set[str]) -> bool:
        return any(
            _hamming_distance(candidate_fingerprint, fingerprint) <= 5
            for fingerprint in existing_fingerprints
        )


def _hamming_distance(left: str, right: str) -> int:
    left_bits = bin(int(left, 16))[2:].zfill(len(left) * 4)
    right_bits = bin(int(right, 16))[2:].zfill(len(right) * 4)
    return sum(1 for a, b in zip(left_bits, right_bits) if a != b)
