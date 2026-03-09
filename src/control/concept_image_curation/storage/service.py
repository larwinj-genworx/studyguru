from __future__ import annotations

import io
import logging
from dataclasses import dataclass

import httpx
from PIL import Image, ImageFile, ImageStat

from src.config.settings import Settings

from ..models import PageImageCandidate


logger = logging.getLogger("uvicorn.error")
ImageFile.LOAD_TRUNCATED_IMAGES = False


@dataclass(slots=True)
class StoredConceptImage:
    relative_image_path: str
    relative_thumbnail_path: str
    mime_type: str
    width: int
    height: int
    file_size_bytes: int
    fingerprint: str


class ConceptImageStorageService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }

    async def download_and_store(
        self,
        *,
        candidate: PageImageCandidate,
        subject_id: str,
        concept_material_id: str,
        image_id: str,
    ) -> StoredConceptImage | None:
        timeout = httpx.Timeout(max(self.settings.resource_search_timeout_seconds, 8))
        headers = {**self._headers, "Referer": candidate.source_page_url}
        try:
            async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
                response = await client.get(candidate.source_image_url)
            if response.status_code >= 400:
                return None
            content_type = response.headers.get("content-type", "")
            if not content_type.startswith("image/"):
                return None
            return await self._store_bytes(
                data=response.content,
                mime_type=content_type.split(";")[0].strip() or "image/webp",
                subject_id=subject_id,
                concept_material_id=concept_material_id,
                image_id=image_id,
            )
        except Exception as exc:
            logger.warning("[ConceptImageStorage] Download failed for %s: %s", candidate.source_image_url, exc)
            return None

    async def _store_bytes(
        self,
        *,
        data: bytes,
        mime_type: str,
        subject_id: str,
        concept_material_id: str,
        image_id: str,
    ) -> StoredConceptImage | None:
        try:
            image = Image.open(io.BytesIO(data))
            image.load()
        except Exception:
            return None

        width, height = image.size
        if width < self.settings.concept_image_min_width or height < self.settings.concept_image_min_height:
            return None

        aspect_ratio = width / max(height, 1)
        if aspect_ratio < 0.45 or aspect_ratio > 2.8:
            return None
        if self._is_low_information_image(image):
            return None

        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")

        fingerprint = self._average_hash(image)
        output_dir = self.settings.concept_image_output_dir / subject_id / concept_material_id
        thumb_dir = output_dir / "thumbs"
        output_dir.mkdir(parents=True, exist_ok=True)
        thumb_dir.mkdir(parents=True, exist_ok=True)

        lossless = image.mode == "RGBA"
        full_path = output_dir / f"{image_id}.webp"
        thumb_path = thumb_dir / f"{image_id}.webp"
        image.save(full_path, format="WEBP", quality=90, method=6, lossless=lossless)
        thumb_image = image.copy()
        thumb_image.thumbnail((640, 640))
        thumb_image.save(thumb_path, format="WEBP", quality=84, method=4, lossless=lossless)

        relative_full = str(full_path.relative_to(self.settings.concept_image_output_dir)).replace("\\", "/")
        relative_thumb = str(thumb_path.relative_to(self.settings.concept_image_output_dir)).replace("\\", "/")
        logger.info(
            "[ConceptImageStorage] Image stored. source=%s output=%s size=%dx%d",
            image_id,
            relative_full,
            width,
            height,
        )
        return StoredConceptImage(
            relative_image_path=relative_full,
            relative_thumbnail_path=relative_thumb,
            mime_type=mime_type or "image/webp",
            width=width,
            height=height,
            file_size_bytes=len(data),
            fingerprint=fingerprint,
        )

    def remove_paths(self, *relative_paths: str) -> None:
        for relative_path in relative_paths:
            if not relative_path:
                continue
            try:
                target = self._resolve_relative_path(relative_path)
            except ValueError as exc:
                logger.warning("[ConceptImageStorage] Refused to remove unsafe path '%s': %s", relative_path, exc)
                continue
            try:
                if target.exists():
                    target.unlink()
            except Exception as exc:
                logger.warning("[ConceptImageStorage] Failed to remove %s: %s", target, exc)

    @staticmethod
    def _average_hash(image: Image.Image, hash_size: int = 8) -> str:
        grayscale = image.convert("L").resize((hash_size, hash_size))
        pixels = list(grayscale.getdata())
        avg = sum(pixels) / max(len(pixels), 1)
        bits = ["1" if value >= avg else "0" for value in pixels]
        bit_string = "".join(bits)
        return f"{int(bit_string, 2):0{hash_size * hash_size // 4}x}"

    @staticmethod
    def _is_low_information_image(image: Image.Image) -> bool:
        sample = image.convert("L").resize((96, 96))
        pixels = list(sample.getdata())
        if not pixels:
            return True
        stat = ImageStat.Stat(sample)
        stddev = stat.stddev[0] if stat.stddev else 0.0
        near_white_ratio = sum(1 for pixel in pixels if pixel >= 248) / len(pixels)
        near_black_ratio = sum(1 for pixel in pixels if pixel <= 8) / len(pixels)
        if stddev < 6:
            return True
        if near_white_ratio > 0.985 and stddev < 14:
            return True
        if near_black_ratio > 0.985 and stddev < 14:
            return True
        return False

    def _resolve_relative_path(self, relative_path: str):
        base_dir = self.settings.concept_image_output_dir.resolve()
        target = (base_dir / relative_path).resolve()
        if not str(target).startswith(str(base_dir)):
            raise ValueError("Unsafe image path.")
        return target
