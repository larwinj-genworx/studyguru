from __future__ import annotations

import mimetypes
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path, PurePosixPath
from typing import Iterator

from fastapi import HTTPException, status
from fastapi.responses import FileResponse, Response, StreamingResponse

from src.config.settings import Settings, get_settings

_STORAGE_SCOPES = ("https://www.googleapis.com/auth/devstorage.read_write",)
_MATERIAL_AREA = "study_material"
_CONCEPT_VISUAL_AREA = "concept_visuals"
_STREAM_CHUNK_SIZE = 1024 * 1024

class ObjectStorageService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = None
        self._bucket = None

    @property
    def material_area(self) -> str:
        return _MATERIAL_AREA

    @property
    def concept_visual_area(self) -> str:
        return _CONCEPT_VISUAL_AREA

    def upload_local_directory(self, area: str, local_dir: Path, *, local_root: Path | None = None) -> None:
        if not self.settings.gcs_enabled:
            return
        root = (local_root or self._local_root(area)).resolve()
        directory = local_dir.resolve()
        if not directory.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")
        files = sorted(path for path in directory.rglob("*") if path.is_file())
        if not files:
            return
        workers = max(self.settings.gcs_upload_workers, 1)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self.upload_local_file, area, path.relative_to(root).as_posix(), path): path
                for path in files
            }
            for future in as_completed(futures):
                future.result()

    def upload_local_file(
        self,
        area: str,
        relative_path: str,
        local_path: Path,
        *,
        content_type: str | None = None,
    ) -> None:
        if not self.settings.gcs_enabled:
            return
        object_name = self._object_name(area, relative_path)
        blob = self._bucket_client().blob(object_name)
        resolved_type = content_type or mimetypes.guess_type(local_path.name)[0] or "application/octet-stream"
        blob.cache_control = self._cache_control_for(local_path.name)
        blob.upload_from_filename(
            filename=str(local_path),
            content_type=resolved_type,
            timeout=self.settings.gcs_request_timeout_seconds,
        )

    def ensure_local_copy(
        self,
        area: str,
        relative_path: str,
        *,
        local_path: Path | None = None,
    ) -> Path:
        normalized = self._normalize_relative_path(relative_path)
        target = (local_path or self._local_path(area, normalized)).resolve()
        if target.exists():
            return target
        if not self.settings.gcs_enabled:
            raise FileNotFoundError(f"Stored file not found: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        blob = self._get_blob_or_none(area, normalized)
        if blob is None:
            raise FileNotFoundError(f"GCS object not found: {normalized}")
        blob.download_to_filename(str(target), timeout=self.settings.gcs_request_timeout_seconds)
        return target

    def ensure_local_prefix(
        self,
        area: str,
        relative_prefix: str,
        *,
        local_root: Path | None = None,
    ) -> Path:
        normalized_prefix = self._normalize_relative_path(relative_prefix)
        root = (local_root or self._local_root(area)).resolve()
        target = (root / normalized_prefix).resolve()
        if not self.settings.gcs_enabled:
            if target.exists():
                return target
            raise FileNotFoundError(f"Stored directory not found: {target}")

        prefix = f"{self._object_name(area, normalized_prefix).rstrip('/')}/"
        area_prefix = f"{self._area_prefix(area).rstrip('/')}/"
        found = False
        for blob in self._bucket_client().list_blobs(prefix=prefix):
            if blob.name.endswith("/"):
                continue
            found = True
            relative_path = blob.name[len(area_prefix):]
            local_path = (root / relative_path).resolve()
            local_path.parent.mkdir(parents=True, exist_ok=True)
            blob.download_to_filename(str(local_path), timeout=self.settings.gcs_request_timeout_seconds)
        if not found and not target.exists():
            raise FileNotFoundError(f"GCS prefix not found: {normalized_prefix}")
        return target

    def delete_file(self, area: str, relative_path: str, *, local_path: Path | None = None) -> None:
        normalized = self._normalize_relative_path(relative_path)
        target = local_path or self._local_path(area, normalized)
        if target.exists():
            target.unlink(missing_ok=True)
        if not self.settings.gcs_enabled:
            return
        blob = self._bucket_client().blob(self._object_name(area, normalized))
        if blob.exists(timeout=self.settings.gcs_request_timeout_seconds):
            blob.delete(timeout=self.settings.gcs_request_timeout_seconds)

    def delete_prefix(self, area: str, relative_prefix: str) -> None:
        normalized_prefix = self._normalize_relative_path(relative_prefix)
        if self.settings.gcs_enabled:
            prefix = f"{self._object_name(area, normalized_prefix).rstrip('/')}/"
            for blob in self._bucket_client().list_blobs(prefix=prefix):
                blob.delete(timeout=self.settings.gcs_request_timeout_seconds)
        target = self._local_path(area, normalized_prefix)
        if target.exists() and target.is_dir():
            for child in sorted(target.rglob("*"), reverse=True):
                if child.is_file():
                    child.unlink(missing_ok=True)
                elif child.is_dir():
                    child.rmdir()
            target.rmdir()

    def build_download_response(
        self,
        area: str,
        relative_path: str,
        *,
        download_name: str | None = None,
        media_type: str | None = None,
        local_path: Path | None = None,
        inline: bool = False,
    ) -> Response:
        normalized = self._normalize_relative_path(relative_path)
        filename = download_name or Path(normalized).name
        fallback_local_path = local_path or self._local_path(area, normalized)

        if self.settings.gcs_enabled:
            blob = self._get_blob_or_none(area, normalized)
            if blob is not None:
                blob.reload(timeout=self.settings.gcs_request_timeout_seconds)
                resolved_media_type = (
                    media_type
                    or blob.content_type
                    or mimetypes.guess_type(filename)[0]
                    or "application/octet-stream"
                )
                headers = {
                    "Content-Disposition": self._content_disposition(filename, inline=inline),
                }
                if blob.size is not None:
                    headers["Content-Length"] = str(blob.size)
                return StreamingResponse(
                    self._stream_blob(blob),
                    media_type=resolved_media_type,
                    headers=headers,
                )

        path = self.ensure_local_copy(area, normalized, local_path=fallback_local_path)
        return FileResponse(path=str(path), filename=filename, media_type=media_type)

    def read_text(
        self,
        area: str,
        relative_path: str,
        *,
        encoding: str = "utf-8",
        local_path: Path | None = None,
    ) -> str:
        path = self.ensure_local_copy(area, relative_path, local_path=local_path)
        return path.read_text(encoding=encoding)

    def sync_local_file(self, area: str, local_path: Path, *, local_root: Path | None = None) -> None:
        if not self.settings.gcs_enabled:
            return
        root = (local_root or self._local_root(area)).resolve()
        path = local_path.resolve()
        self.upload_local_file(area, path.relative_to(root).as_posix(), path)

    def _stream_blob(self, blob) -> Iterator[bytes]:
        blob.chunk_size = _STREAM_CHUNK_SIZE
        handle = blob.open("rb")
        try:
            while True:
                chunk = handle.read(_STREAM_CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk
        finally:
            handle.close()

    def _bucket_client(self):
        if self._bucket is not None:
            return self._bucket
        try:
            import google.auth
            from google.auth import impersonated_credentials
            from google.cloud import storage
        except ImportError as exc:  # pragma: no cover - dependency is runtime configured
            raise RuntimeError(
                "Missing dependency 'google-cloud-storage'. Install backend dependencies before enabling GCS."
            ) from exc

        source_credentials, detected_project = google.auth.default(scopes=_STORAGE_SCOPES)
        active_project = self.settings.gcs_project_id or detected_project
        if not active_project:
            raise RuntimeError("Unable to determine the Google Cloud project for artifact storage.")

        credentials = source_credentials
        if (self.settings.gcs_target_service_account or "").strip():
            credentials = impersonated_credentials.Credentials(
                source_credentials=source_credentials,
                target_principal=self.settings.gcs_target_service_account.strip(),
                target_scopes=list(_STORAGE_SCOPES),
                lifetime=3600,
            )

        self._client = storage.Client(project=active_project, credentials=credentials)
        self._bucket = self._client.bucket(self.settings.gcs_bucket_name)
        return self._bucket

    def _get_blob_or_none(self, area: str, relative_path: str):
        if not self.settings.gcs_enabled:
            return None
        blob = self._bucket_client().blob(self._object_name(area, relative_path))
        if not blob.exists(timeout=self.settings.gcs_request_timeout_seconds):
            return None
        return blob

    def _local_root(self, area: str) -> Path:
        if area == _MATERIAL_AREA:
            return self.settings.material_output_dir
        if area == _CONCEPT_VISUAL_AREA:
            return self.settings.concept_visual_output_dir
        raise ValueError(f"Unsupported storage area: {area}")

    def _local_path(self, area: str, relative_path: str) -> Path:
        return self._local_root(area) / self._normalize_relative_path(relative_path)

    def _area_prefix(self, area: str) -> str:
        cleaned_prefix = self.settings.gcs_bucket_prefix.strip("/")
        if cleaned_prefix:
            return f"{cleaned_prefix}/{area}"
        return area

    def _object_name(self, area: str, relative_path: str) -> str:
        normalized = self._normalize_relative_path(relative_path)
        return f"{self._area_prefix(area).rstrip('/')}/{normalized}"

    @staticmethod
    def _normalize_relative_path(value: str) -> str:
        cleaned = (value or "").replace("\\", "/").strip("/")
        if not cleaned:
            raise ValueError("Storage path cannot be empty.")
        path = PurePosixPath(cleaned)
        if path.is_absolute():
            raise ValueError("Storage paths must be relative.")
        parts = path.parts
        if any(part in ("", ".", "..") for part in parts):
            raise ValueError("Unsafe storage path.")
        if any(part.endswith(":") for part in parts):
            raise ValueError("Unsafe storage path.")
        return "/".join(parts)

    @staticmethod
    def _cache_control_for(filename: str) -> str:
        ext = Path(filename).suffix.lower()
        if ext in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".pdf"}:
            return "private, max-age=3600"
        return "private, max-age=300"

    @staticmethod
    def _content_disposition(filename: str, *, inline: bool) -> str:
        safe_name = filename.replace('"', "").strip() or "download"
        disposition = "inline" if inline else "attachment"
        return f'{disposition}; filename="{safe_name}"'


_service = ObjectStorageService(get_settings())


def get_object_storage_service() -> ObjectStorageService:
    return _service
