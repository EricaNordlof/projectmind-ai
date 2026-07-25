from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(value, maximum))


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_password: str
    session_secret: str
    session_secure: bool
    openai_api_key: str
    openai_model: str
    openai_reasoning_effort: str
    openai_max_output_tokens: int
    data_dir: Path
    database_url: str
    storage_backend: str
    s3_endpoint_url: str | None
    s3_bucket: str
    s3_region: str
    aws_access_key_id: str
    aws_secret_access_key: str
    s3_force_path_style: bool
    persistent_disk: bool
    max_upload_mb: int
    max_chat_image_mb: int
    max_chat_images: int
    smart_context_max_chars: int
    smart_max_file_chars: int
    smart_history_messages: int

    @property
    def using_postgres(self) -> bool:
        return self.database_url.startswith(("postgresql://", "postgresql+psycopg://"))

    @property
    def using_local_persistent_disk(self) -> bool:
        return (
            self.storage_backend == "local"
            and self.persistent_disk
            and str(self.data_dir).startswith("/app/storage")
        )

    @property
    def persistence_ok(self) -> bool:
        return (
            (self.using_postgres and self.storage_backend == "s3")
            or self.using_local_persistent_disk
        )

    @property
    def persistence_mode(self) -> str:
        if self.using_postgres and self.storage_backend == "s3":
            return "production"
        if self.using_local_persistent_disk:
            return "persistent_disk"
        return "development"

    @property
    def persistence_title(self) -> str:
        if self.persistence_mode == "production":
            return "Produktionslagring aktiv"
        if self.persistence_mode == "persistent_disk":
            return "Permanent lagring aktiv"
        return "Lagringen är inte permanent"

    @property
    def persistence_message(self) -> str:
        if self.persistence_mode == "production":
            return "Projektdata sparas i PostgreSQL och uppladdade filer i privat S3-lagring."
        if self.persistence_mode == "persistent_disk":
            return "Projekt, chattar och filer sparas på Render-disken under /app/storage."
        return "Appen använder lokal lagring utan bekräftad persistent disk. Data kan försvinna vid omstart eller deploy."


def load_settings() -> Settings:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url.startswith("postgres://"):
        database_url = "postgresql://" + database_url[len("postgres://"):]

    data_dir = Path(os.getenv("DATA_DIR", "./storage")).expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    return Settings(
        app_name=os.getenv("APP_NAME", "ProjectMind AI").strip() or "ProjectMind AI",
        app_password=os.getenv("APP_PASSWORD", "").strip(),
        session_secret=os.getenv("SESSION_SECRET", "").strip() or "change-this-session-secret",
        session_secure=_bool("SESSION_SECURE", False),
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.6-sol").strip() or "gpt-5.6-sol",
        openai_reasoning_effort=os.getenv("OPENAI_REASONING_EFFORT", "max").strip().lower(),
        openai_max_output_tokens=_int("OPENAI_MAX_OUTPUT_TOKENS", 8000, 1000, 32000),
        data_dir=data_dir,
        database_url=database_url,
        storage_backend=os.getenv("STORAGE_BACKEND", "local").strip().lower(),
        s3_endpoint_url=os.getenv("S3_ENDPOINT_URL", "").strip() or None,
        s3_bucket=os.getenv("S3_BUCKET", "").strip(),
        s3_region=os.getenv("S3_REGION", "eu-central-1").strip() or "eu-central-1",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "").strip(),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "").strip(),
        s3_force_path_style=_bool("S3_FORCE_PATH_STYLE", False),
        persistent_disk=_bool("PERSISTENT_DISK", False),
        max_upload_mb=_int("MAX_UPLOAD_MB", 100, 1, 500),
        max_chat_image_mb=_int("MAX_CHAT_IMAGE_MB", 12, 1, 25),
        max_chat_images=_int("MAX_CHAT_IMAGES", 4, 1, 8),
        smart_context_max_chars=_int("SMART_CONTEXT_MAX_CHARS", 180000, 50000, 500000),
        smart_max_file_chars=_int("SMART_MAX_FILE_CHARS", 120000, 10000, 300000),
        smart_history_messages=_int("SMART_HISTORY_MESSAGES", 40, 10, 100),
    )


settings = load_settings()
