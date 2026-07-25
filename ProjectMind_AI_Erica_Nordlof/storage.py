from __future__ import annotations

import mimetypes
import re
import shutil
import tempfile
from pathlib import Path
from typing import Iterator

import boto3
from botocore.exceptions import ClientError
from fastapi import HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from config import settings


UPLOAD_DIR = settings.data_dir / "uploads"
VERSION_DIR = settings.data_dir / "versions"
CHAT_UPLOAD_DIR = settings.data_dir / "chat_uploads"
for directory in (UPLOAD_DIR, VERSION_DIR, CHAT_UPLOAD_DIR):
    directory.mkdir(parents=True, exist_ok=True)


def safe_filename(name: str) -> str:
    value = Path(name).name.strip()
    value = re.sub(r"[^A-Za-z0-9._()\- åäöÅÄÖ]", "_", value)
    value = re.sub(r"_+", "_", value)
    return value[:180] or "fil"


def _base(kind: str) -> Path:
    mapping = {
        "uploads": UPLOAD_DIR,
        "versions": VERSION_DIR,
        "chat_uploads": CHAT_UPLOAD_DIR,
    }
    if kind not in mapping:
        raise ValueError(f"Okänd lagringstyp: {kind}")
    return mapping[kind]


def local_path(kind: str, owner_id: str, stored_name: str) -> Path:
    return _base(kind) / owner_id / stored_name


def storage_key(kind: str, owner_id: str, stored_name: str) -> str:
    return f"projectmind/{kind}/{owner_id}/{stored_name}"


def s3_client():
    if settings.storage_backend != "s3":
        return None
    if not settings.s3_bucket or not settings.aws_access_key_id or not settings.aws_secret_access_key:
        raise RuntimeError("S3 är valt men S3_BUCKET/AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY saknas.")
    config = None
    if settings.s3_force_path_style:
        from botocore.config import Config
        config = Config(s3={"addressing_style": "path"})
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        region_name=settings.s3_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        config=config,
    )


async def save_upload(
    upload: UploadFile,
    kind: str,
    owner_id: str,
    stored_name: str,
    max_bytes: int,
) -> int:
    temp = tempfile.NamedTemporaryFile(delete=False)
    temp_path = Path(temp.name)
    total = 0
    try:
        with temp:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Filen är större än {max_bytes // (1024 * 1024)} MB.",
                    )
                temp.write(chunk)
        await upload.close()

        if settings.storage_backend == "s3":
            client = s3_client()
            client.upload_file(
                str(temp_path),
                settings.s3_bucket,
                storage_key(kind, owner_id, stored_name),
                ExtraArgs={
                    "ContentType": upload.content_type or "application/octet-stream",
                    "ServerSideEncryption": "AES256",
                },
            )
            return total

        destination = local_path(kind, owner_id, stored_name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(temp_path), destination)
        return total
    finally:
        temp_path.unlink(missing_ok=True)


def exists(kind: str, owner_id: str, stored_name: str) -> bool:
    if settings.storage_backend == "s3":
        try:
            s3_client().head_object(
                Bucket=settings.s3_bucket,
                Key=storage_key(kind, owner_id, stored_name),
            )
            return True
        except ClientError:
            return False
    return local_path(kind, owner_id, stored_name).exists()


def read_bytes(kind: str, owner_id: str, stored_name: str) -> bytes:
    if settings.storage_backend == "s3":
        response = s3_client().get_object(
            Bucket=settings.s3_bucket,
            Key=storage_key(kind, owner_id, stored_name),
        )
        return response["Body"].read()
    path = local_path(kind, owner_id, stored_name)
    if not path.exists():
        raise FileNotFoundError(path)
    return path.read_bytes()


def download_response(
    kind: str,
    owner_id: str,
    stored_name: str,
    original_name: str,
    media_type: str | None = None,
    inline: bool = False,
):
    media_type = media_type or mimetypes.guess_type(original_name)[0] or "application/octet-stream"
    disposition = "inline" if inline else "attachment"
    safe = safe_filename(original_name).replace('"', "")

    if settings.storage_backend == "s3":
        response = s3_client().get_object(
            Bucket=settings.s3_bucket,
            Key=storage_key(kind, owner_id, stored_name),
        )
        return StreamingResponse(
            response["Body"].iter_chunks(chunk_size=1024 * 1024),
            media_type=media_type,
            headers={"Content-Disposition": f'{disposition}; filename="{safe}"'},
        )

    path = local_path(kind, owner_id, stored_name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Filen saknas på lagringen.")
    if inline:
        return FileResponse(path, media_type=media_type, headers={"Content-Disposition": f'inline; filename="{safe}"'})
    return FileResponse(path, filename=original_name, media_type=media_type)


def delete(kind: str, owner_id: str, stored_name: str) -> None:
    if settings.storage_backend == "s3":
        s3_client().delete_object(
            Bucket=settings.s3_bucket,
            Key=storage_key(kind, owner_id, stored_name),
        )
        return
    local_path(kind, owner_id, stored_name).unlink(missing_ok=True)


def delete_prefix(kind: str, owner_id: str) -> None:
    if settings.storage_backend == "s3":
        client = s3_client()
        prefix = storage_key(kind, owner_id, "")
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=settings.s3_bucket, Prefix=prefix):
            objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
            if objects:
                client.delete_objects(Bucket=settings.s3_bucket, Delete={"Objects": objects})
        return
    shutil.rmtree(_base(kind) / owner_id, ignore_errors=True)


def healthcheck() -> tuple[bool, str]:
    try:
        if settings.storage_backend == "s3":
            s3_client().head_bucket(Bucket=settings.s3_bucket)
        else:
            settings.data_dir.mkdir(parents=True, exist_ok=True)
            probe = settings.data_dir / ".healthcheck"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        return True, ""
    except Exception as exc:
        return False, str(exc)
