from __future__ import annotations

import mimetypes
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


PROJECT_ID = "gwx-internship-01"
BUCKET_NAME = "gwx_stg_intern-01"
BUCKET_PREFIX = "studyguru"
SOURCE_DIR = Path(__file__).resolve().parent / "output"
WORKERS = 8
TARGET_SERVICE_ACCOUNT = "gwx-cloudrun-sa-01@gwx-internship-01.iam.gserviceaccount.com"
SCOPES = ("https://www.googleapis.com/auth/devstorage.read_write",)
logger = logging.getLogger(__name__)


def create_storage_client(project: str):
    try:
        import google.auth
        from google.auth import impersonated_credentials
        from google.cloud import storage
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency 'google-cloud-storage'. "
            "Install it with 'uv add google-cloud-storage' or 'pip install google-cloud-storage'."
        ) from exc

    source_credentials, detected_project = google.auth.default(scopes=SCOPES)
    active_project = project or detected_project
    if not active_project:
        raise RuntimeError(
            "Unable to determine the Google Cloud project. "
            "Set PROJECT_ID explicitly in the script."
        )
    if TARGET_SERVICE_ACCOUNT:
        credentials = impersonated_credentials.Credentials(
            source_credentials=source_credentials,
            target_principal=TARGET_SERVICE_ACCOUNT,
            target_scopes=list(SCOPES),
            lifetime=3600,
        )
        return storage.Client(project=active_project, credentials=credentials)
    return storage.Client(project=active_project, credentials=source_credentials)


def build_object_name(root: Path, file_path: Path) -> str:
    relative_path = file_path.relative_to(root).as_posix()
    return "/".join(part for part in (BUCKET_PREFIX.strip("/"), relative_path) if part)


def upload_file(bucket, root: Path, file_path: Path) -> str:
    object_name = build_object_name(root, file_path)
    blob = bucket.blob(object_name)
    content_type, _ = mimetypes.guess_type(file_path.name)
    blob.upload_from_filename(
        filename=str(file_path),
        content_type=content_type,
        timeout=300,
    )
    return object_name


def main() -> int:
    root = SOURCE_DIR.resolve()
    if not root.exists():
        raise FileNotFoundError(f"Backend output folder not found: {root}")

    files = sorted(path for path in root.rglob("*") if path.is_file())
    if not files:
        logger.info("No files found for upload.", extra={"source_dir": str(root)})
        return 0

    client = create_storage_client(PROJECT_ID)
    bucket = client.bucket(BUCKET_NAME)

    total_bytes = sum(path.stat().st_size for path in files)
    logger.info(
        "Starting bulk upload.",
        extra={
            "source_dir": str(root),
            "project_id": PROJECT_ID,
            "bucket_name": BUCKET_NAME,
            "bucket_prefix": BUCKET_PREFIX,
            "target_service_account": TARGET_SERVICE_ACCOUNT,
            "file_count": len(files),
            "total_bytes": total_bytes,
        },
    )

    uploaded = 0
    with ThreadPoolExecutor(max_workers=max(WORKERS, 1)) as executor:
        future_map = {
            executor.submit(upload_file, bucket, root, file_path): file_path
            for file_path in files
        }
        for future in as_completed(future_map):
            object_name = future.result()
            uploaded += 1
            logger.info("Uploaded file to object storage.", extra={"object_name": object_name})

    logger.info(
        "Completed bulk upload.",
        extra={
            "uploaded_files": uploaded,
            "bucket_name": BUCKET_NAME,
            "bucket_prefix": BUCKET_PREFIX,
        },
    )
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
