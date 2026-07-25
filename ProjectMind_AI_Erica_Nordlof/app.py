from __future__ import annotations

import hmac
import mimetypes
import secrets
import uuid
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.middleware.sessions import SessionMiddleware

from ai_service import ask_ai
from config import settings
from db import connection, execute, fetchall, fetchone
from documents import SUPPORTED_EXTENSIONS, build_project_context, index_file, reindex_project
from markdown_utils import render_markdown
from storage import (
    delete as storage_delete,
    delete_prefix as storage_delete_prefix,
    download_response,
    healthcheck as storage_healthcheck,
    read_bytes,
    safe_filename,
    save_upload,
)


BASE_DIR = Path(__file__).parent.resolve()
app = FastAPI(title=settings.app_name)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    https_only=settings.session_secure,
    same_site="lax",
    session_cookie="projectmind_session",
    max_age=60 * 60 * 24 * 14,
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

templates = Environment(
    loader=FileSystemLoader(BASE_DIR / "templates"),
    autoescape=select_autoescape(["html", "xml"]),
)

ALLOWED_EXTENSIONS = {
    ".zip", ".txt", ".md", ".json", ".csv", ".html", ".htm", ".css", ".js", ".mjs", ".cjs",
    ".ts", ".tsx", ".jsx", ".py", ".java", ".xml", ".yaml", ".yml", ".toml", ".ini", ".sql",
    ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".docx", ".xlsx", ".pptx",
}
ALLOWED_IMAGE_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
MAX_UPLOAD_BYTES = settings.max_upload_mb * 1024 * 1024
MAX_CHAT_IMAGE_BYTES = settings.max_chat_image_mb * 1024 * 1024


def uid() -> str:
    return uuid.uuid4().hex


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def format_bytes(value: int | str | None) -> str:
    try:
        size = int(value or 0)
    except (TypeError, ValueError):
        return "0 B"
    units = ["B", "KB", "MB", "GB"]
    amount = float(size)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.0f} {unit}" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{size} B"


def format_date(value: str | None) -> str:
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value


templates.filters["filesize"] = format_bytes
templates.filters["date"] = format_date


def require_admin(request: Request) -> None:
    if not request.session.get("admin"):
        raise HTTPException(status_code=401, detail="Inloggning krävs.")


def verify_csrf(request: Request, token: str) -> None:
    expected = request.session.get("csrf", "")
    if not expected or not token or not hmac.compare_digest(expected, token):
        raise HTTPException(status_code=403, detail="Ogiltig formulärtoken.")


def project_or_404(project_id: str) -> dict[str, Any]:
    project = fetchone("SELECT * FROM projects WHERE id=?", (project_id,))
    if not project:
        raise HTTPException(status_code=404, detail="Projektet hittades inte.")
    return project


def chat_or_404(chat_id: str) -> dict[str, Any]:
    chat = fetchone("SELECT * FROM chats WHERE id=?", (chat_id,))
    if not chat:
        raise HTTPException(status_code=404, detail="Chatten hittades inte.")
    return chat


def render(request: Request, template_name: str, **context: Any) -> HTMLResponse:
    nav_projects: list[dict[str, Any]] = []
    nav_chats: list[dict[str, Any]] = []
    if request.session.get("admin"):
        nav_projects = fetchall(
            "SELECT id,name,status FROM projects ORDER BY updated_at DESC LIMIT 15"
        )
        nav_chats = fetchall(
            """
            SELECT c.id,c.title,c.project_id,p.name AS project_name
            FROM chats c LEFT JOIN projects p ON p.id=c.project_id
            ORDER BY c.updated_at DESC LIMIT 12
            """
        )
    base = {
        "request": request,
        "app_name": settings.app_name,
        "is_admin": bool(request.session.get("admin")),
        "csrf": request.session.get("csrf", ""),
        "nav_projects": nav_projects,
        "nav_chats": nav_chats,
        "persistence_ok": settings.persistence_ok,
        "persistence_mode": settings.persistence_mode,
        "persistence_title": settings.persistence_title,
        "persistence_message": settings.persistence_message,
    }
    base.update(context)
    return HTMLResponse(templates.get_template(template_name).render(**base))


@app.exception_handler(HTTPException)
async def http_exception_page(request: Request, exc: HTTPException):
    if request.url.path == "/health":
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    if exc.status_code == 401:
        return RedirectResponse("/login", status_code=303)
    if request.session.get("admin"):
        return render(
            request,
            "error.html",
            status_code=exc.status_code,
            error_message=str(exc.detail),
        )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/health")
def health():
    database_ok = False
    database_error = ""
    try:
        with connection() as conn:
            conn.execute("SELECT 1")
        database_ok = True
    except Exception as exc:
        database_error = str(exc)

    storage_ok, storage_error = storage_healthcheck()
    status = {
        "ok": database_ok and storage_ok,
        "database": "postgresql" if settings.using_postgres else "sqlite",
        "database_ok": database_ok,
        "storage": settings.storage_backend,
        "storage_ok": storage_ok,
        "persistent": settings.persistence_ok,
        "persistence_mode": settings.persistence_mode,
        "data_dir": str(settings.data_dir),
    }
    errors = [item for item in (database_error, storage_error) if item]
    if errors:
        status["error"] = "; ".join(errors)
    if not status["ok"]:
        raise HTTPException(status_code=503, detail=status)
    return status


@app.get("/login")
def login_page(request: Request):
    if request.session.get("admin"):
        return RedirectResponse("/", status_code=303)
    return render(request, "login.html", error="")


@app.post("/login")
def login(request: Request, password: Annotated[str, Form(...)]):
    if not settings.app_password:
        return render(request, "login.html", error="APP_PASSWORD saknas i serverns miljövariabler.")
    if not hmac.compare_digest(password, settings.app_password):
        return render(request, "login.html", error="Fel lösenord.")
    request.session.clear()
    request.session["admin"] = True
    request.session["csrf"] = secrets.token_urlsafe(32)
    return RedirectResponse("/", status_code=303)


@app.post("/logout")
def logout(request: Request, csrf: Annotated[str, Form(...)]):
    require_admin(request)
    verify_csrf(request, csrf)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/")
def dashboard(request: Request):
    require_admin(request)
    projects = fetchall(
        """
        SELECT p.*,
          (SELECT COUNT(*) FROM project_files f WHERE f.project_id=p.id) AS file_count,
          (SELECT COUNT(*) FROM versions v WHERE v.project_id=p.id) AS version_count,
          (SELECT COUNT(*) FROM chats c WHERE c.project_id=p.id) AS chat_count
        FROM projects p ORDER BY p.updated_at DESC
        """
    )
    chats = fetchall(
        """
        SELECT c.*,p.name AS project_name
        FROM chats c LEFT JOIN projects p ON p.id=c.project_id
        ORDER BY c.updated_at DESC LIMIT 30
        """
    )
    return render(request, "dashboard.html", projects=projects, chats=chats)


@app.post("/projects")
def create_project(
    request: Request,
    csrf: Annotated[str, Form(...)],
    name: Annotated[str, Form(...)],
    description: Annotated[str, Form()] = "",
    stack: Annotated[str, Form()] = "",
):
    require_admin(request)
    verify_csrf(request, csrf)
    project_id = uid()
    timestamp = now()
    execute(
        "INSERT INTO projects(id,name,description,status,stack,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
        (
            project_id,
            name.strip()[:120] or "Projekt",
            description.strip(),
            "active",
            stack.strip(),
            "",
            timestamp,
            timestamp,
        ),
    )
    return RedirectResponse(f"/projects/{project_id}", status_code=303)


@app.get("/projects/{project_id}")
def project_page(request: Request, project_id: str):
    require_admin(request)
    project = project_or_404(project_id)
    files = fetchall(
        """
        SELECT f.*,c.locator_count,c.extraction_error,c.extracted_at,
               CASE WHEN c.file_id IS NULL THEN 0 ELSE 1 END AS indexed
        FROM project_files f
        LEFT JOIN document_text_cache c ON c.file_id=f.id
        WHERE f.project_id=? ORDER BY f.created_at DESC
        """,
        (project_id,),
    )
    versions = fetchall(
        "SELECT * FROM versions WHERE project_id=? ORDER BY created_at DESC",
        (project_id,),
    )
    chats = fetchall(
        "SELECT * FROM chats WHERE project_id=? ORDER BY updated_at DESC",
        (project_id,),
    )
    return render(
        request,
        "project.html",
        project=project,
        files=files,
        versions=versions,
        chats=chats,
        max_upload_mb=settings.max_upload_mb,
        supported_extensions=", ".join(sorted(SUPPORTED_EXTENSIONS)),
    )


@app.post("/projects/{project_id}/update")
def update_project(
    request: Request,
    project_id: str,
    name: Annotated[str, Form(...)],
    csrf: Annotated[str, Form(...)],
    description: Annotated[str, Form()] = "",
    status: Annotated[str, Form()] = "active",
    stack: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
):
    require_admin(request)
    verify_csrf(request, csrf)
    project_or_404(project_id)
    execute(
        "UPDATE projects SET name=?,description=?,status=?,stack=?,notes=?,updated_at=? WHERE id=?",
        (
            name.strip()[:120] or "Projekt",
            description.strip(),
            status.strip()[:40] or "active",
            stack.strip(),
            notes.strip(),
            now(),
            project_id,
        ),
    )
    return RedirectResponse(f"/projects/{project_id}", status_code=303)


@app.post("/projects/{project_id}/delete")
def delete_project(request: Request, project_id: str, csrf: Annotated[str, Form(...)]):
    require_admin(request)
    verify_csrf(request, csrf)
    project_or_404(project_id)
    chat_ids = fetchall("SELECT id FROM chats WHERE project_id=?", (project_id,))
    for chat in chat_ids:
        storage_delete_prefix("chat_uploads", chat["id"])
    storage_delete_prefix("uploads", project_id)
    storage_delete_prefix("versions", project_id)
    execute("DELETE FROM projects WHERE id=?", (project_id,))
    return RedirectResponse("/", status_code=303)


@app.post("/projects/{project_id}/files")
async def upload_project_file(
    request: Request,
    project_id: str,
    csrf: Annotated[str, Form(...)],
    upload: Annotated[UploadFile, File(...)],
):
    require_admin(request)
    verify_csrf(request, csrf)
    project_or_404(project_id)
    original = safe_filename(upload.filename or "fil")
    extension = Path(original).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Filtypen {extension or '(utan ändelse)'} är inte tillåten.")

    file_id = uid()
    stored = f"{file_id}_{original}"
    mime = upload.content_type or mimetypes.guess_type(original)[0] or "application/octet-stream"
    size = await save_upload(upload, "uploads", project_id, stored, MAX_UPLOAD_BYTES)
    record = {
        "id": file_id,
        "project_id": project_id,
        "original_name": original,
        "stored_name": stored,
        "mime_type": mime,
        "size_bytes": size,
        "created_at": now(),
    }
    execute(
        "INSERT INTO project_files(id,project_id,original_name,stored_name,mime_type,size_bytes,created_at) VALUES(?,?,?,?,?,?,?)",
        (
            record["id"], record["project_id"], record["original_name"], record["stored_name"],
            record["mime_type"], record["size_bytes"], record["created_at"],
        ),
    )
    index_file(record)
    execute("UPDATE projects SET updated_at=? WHERE id=?", (now(), project_id))
    return RedirectResponse(f"/projects/{project_id}#files", status_code=303)


@app.get("/files/{file_id}/download")
def download_file(request: Request, file_id: str):
    require_admin(request)
    record = fetchone("SELECT * FROM project_files WHERE id=?", (file_id,))
    if not record:
        raise HTTPException(status_code=404, detail="Filen hittades inte.")
    return download_response(
        "uploads",
        record["project_id"],
        record["stored_name"],
        record["original_name"],
        record["mime_type"],
    )


@app.post("/files/{file_id}/reindex")
def reindex_file_route(request: Request, file_id: str, csrf: Annotated[str, Form(...)]):
    require_admin(request)
    verify_csrf(request, csrf)
    record = fetchone("SELECT * FROM project_files WHERE id=?", (file_id,))
    if not record:
        raise HTTPException(status_code=404, detail="Filen hittades inte.")
    index_file(record, force=True)
    return RedirectResponse(f"/projects/{record['project_id']}#files", status_code=303)


@app.post("/projects/{project_id}/reindex")
def reindex_project_route(request: Request, project_id: str, csrf: Annotated[str, Form(...)]):
    require_admin(request)
    verify_csrf(request, csrf)
    project_or_404(project_id)
    reindex_project(project_id, force=True)
    return RedirectResponse(f"/projects/{project_id}#files", status_code=303)


@app.post("/files/{file_id}/delete")
def delete_file_route(request: Request, file_id: str, csrf: Annotated[str, Form(...)]):
    require_admin(request)
    verify_csrf(request, csrf)
    record = fetchone("SELECT * FROM project_files WHERE id=?", (file_id,))
    if not record:
        raise HTTPException(status_code=404, detail="Filen hittades inte.")
    storage_delete("uploads", record["project_id"], record["stored_name"])
    execute("DELETE FROM project_files WHERE id=?", (file_id,))
    return RedirectResponse(f"/projects/{record['project_id']}#files", status_code=303)


@app.post("/projects/{project_id}/versions")
async def upload_version(
    request: Request,
    project_id: str,
    version_label: Annotated[str, Form(...)],
    csrf: Annotated[str, Form(...)],
    upload: Annotated[UploadFile, File(...)],
    comment: Annotated[str, Form()] = "",
):
    require_admin(request)
    verify_csrf(request, csrf)
    project_or_404(project_id)
    original = safe_filename(upload.filename or "version.zip")
    if Path(original).suffix.lower() != ".zip":
        raise HTTPException(status_code=400, detail="Projektversioner måste laddas upp som ZIP.")
    version_id = uid()
    stored = f"{version_id}_{original}"
    size = await save_upload(upload, "versions", project_id, stored, MAX_UPLOAD_BYTES)

    try:
        raw = read_bytes("versions", project_id, stored)
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            for info in archive.infolist():
                candidate = Path(info.filename)
                if candidate.is_absolute() or ".." in candidate.parts:
                    raise HTTPException(status_code=400, detail="ZIP-filen innehåller en osäker sökväg.")
    except zipfile.BadZipFile as exc:
        storage_delete("versions", project_id, stored)
        raise HTTPException(status_code=400, detail="Ogiltig ZIP-fil.") from exc
    except Exception:
        storage_delete("versions", project_id, stored)
        raise

    execute(
        "INSERT INTO versions(id,project_id,version_label,comment,original_name,stored_name,size_bytes,created_at) VALUES(?,?,?,?,?,?,?,?)",
        (
            version_id,
            project_id,
            version_label.strip()[:80] or "Version",
            comment.strip(),
            original,
            stored,
            size,
            now(),
        ),
    )
    execute("UPDATE projects SET updated_at=? WHERE id=?", (now(), project_id))
    return RedirectResponse(f"/projects/{project_id}#versions", status_code=303)


@app.get("/versions/{version_id}/download")
def download_version(request: Request, version_id: str):
    require_admin(request)
    record = fetchone("SELECT * FROM versions WHERE id=?", (version_id,))
    if not record:
        raise HTTPException(status_code=404, detail="Versionen hittades inte.")
    return download_response(
        "versions",
        record["project_id"],
        record["stored_name"],
        record["original_name"],
        "application/zip",
    )


@app.post("/versions/{version_id}/delete")
def delete_version(request: Request, version_id: str, csrf: Annotated[str, Form(...)]):
    require_admin(request)
    verify_csrf(request, csrf)
    record = fetchone("SELECT * FROM versions WHERE id=?", (version_id,))
    if not record:
        raise HTTPException(status_code=404, detail="Versionen hittades inte.")
    storage_delete("versions", record["project_id"], record["stored_name"])
    execute("DELETE FROM versions WHERE id=?", (version_id,))
    return RedirectResponse(f"/projects/{record['project_id']}#versions", status_code=303)


@app.post("/chats")
def create_chat(
    request: Request,
    csrf: Annotated[str, Form(...)],
    title: Annotated[str, Form()] = "Ny chatt",
    project_id: Annotated[str, Form()] = "",
):
    require_admin(request)
    verify_csrf(request, csrf)
    project_value = project_id.strip() or None
    if project_value:
        project_or_404(project_value)
    chat_id = uid()
    timestamp = now()
    execute(
        "INSERT INTO chats(id,project_id,title,created_at,updated_at) VALUES(?,?,?,?,?)",
        (chat_id, project_value, title.strip()[:120] or "Ny chatt", timestamp, timestamp),
    )
    return RedirectResponse(f"/chats/{chat_id}", status_code=303)


@app.get("/chats/{chat_id}")
def chat_page(request: Request, chat_id: str):
    require_admin(request)
    chat = chat_or_404(chat_id)
    project = (
        fetchone("SELECT * FROM projects WHERE id=?", (chat["project_id"],))
        if chat["project_id"]
        else None
    )
    messages = fetchall(
        "SELECT * FROM messages WHERE chat_id=? ORDER BY created_at ASC",
        (chat_id,),
    )
    attachments = fetchall(
        "SELECT * FROM chat_attachments WHERE chat_id=? ORDER BY created_at ASC",
        (chat_id,),
    )
    attachments_by_message: dict[str, list[dict[str, Any]]] = {}
    for attachment in attachments:
        attachments_by_message.setdefault(attachment["message_id"], []).append(attachment)
    for message in messages:
        message["rendered"] = render_markdown(message["content"])
    projects = fetchall("SELECT id,name FROM projects ORDER BY updated_at DESC")
    return render(
        request,
        "chat.html",
        chat=chat,
        project=project,
        messages=messages,
        attachments_by_message=attachments_by_message,
        projects=projects,
        max_chat_image_mb=settings.max_chat_image_mb,
        max_chat_images=settings.max_chat_images,
    )


@app.get("/chat-images/{attachment_id}")
def chat_image(request: Request, attachment_id: str):
    require_admin(request)
    record = fetchone("SELECT * FROM chat_attachments WHERE id=?", (attachment_id,))
    if not record:
        raise HTTPException(status_code=404, detail="Bilden hittades inte.")
    return download_response(
        "chat_uploads",
        record["chat_id"],
        record["stored_name"],
        record["original_name"],
        record["mime_type"],
        inline=True,
    )


@app.post("/chats/{chat_id}/message")
async def send_message(
    request: Request,
    chat_id: str,
    csrf: Annotated[str, Form(...)],
    content: Annotated[str, Form()] = "",
    images: list[UploadFile] = File(default=[]),
):
    require_admin(request)
    verify_csrf(request, csrf)
    chat = chat_or_404(chat_id)
    user_text = content.strip()
    real_images = [image for image in images if image and image.filename]
    if not user_text and not real_images:
        return RedirectResponse(f"/chats/{chat_id}", status_code=303)
    if len(real_images) > settings.max_chat_images:
        raise HTTPException(status_code=400, detail=f"Du kan bifoga högst {settings.max_chat_images} bilder.")

    message_id = uid()
    display_text = user_text or "Bild bifogad"
    execute(
        "INSERT INTO messages(id,chat_id,role,content,created_at) VALUES(?,?,?,?,?)",
        (message_id, chat_id, "user", display_text, now()),
    )

    saved_images: list[dict[str, Any]] = []
    try:
        for upload in real_images:
            content_type = (upload.content_type or "").lower()
            if content_type not in ALLOWED_IMAGE_TYPES:
                raise HTTPException(status_code=400, detail="Chatten accepterar PNG, JPG/JPEG, WEBP och GIF.")
            original = safe_filename(upload.filename or "bild.png")
            expected_extension = ALLOWED_IMAGE_TYPES[content_type]
            valid_extensions = {expected_extension, ".jpeg"} if expected_extension == ".jpg" else {expected_extension}
            if Path(original).suffix.lower() not in valid_extensions:
                original = f"{Path(original).stem}{expected_extension}"
            attachment_id = uid()
            stored = f"{attachment_id}_{original}"
            total = await save_upload(
                upload,
                "chat_uploads",
                chat_id,
                stored,
                MAX_CHAT_IMAGE_BYTES,
            )
            record = {
                "id": attachment_id,
                "message_id": message_id,
                "chat_id": chat_id,
                "original_name": original,
                "stored_name": stored,
                "mime_type": content_type,
                "size_bytes": total,
                "created_at": now(),
            }
            execute(
                "INSERT INTO chat_attachments(id,message_id,chat_id,original_name,stored_name,mime_type,size_bytes,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    record["id"], record["message_id"], record["chat_id"], record["original_name"],
                    record["stored_name"], record["mime_type"], record["size_bytes"], record["created_at"],
                ),
            )
            saved_images.append(record)

        history = fetchall(
            "SELECT role,content FROM messages WHERE chat_id=? ORDER BY created_at ASC",
            (chat_id,),
        )
        try:
            context = build_project_context(chat.get("project_id"), user_text)
            answer = await ask_ai(history, context, current_images=saved_images)
        except RuntimeError as exc:
            answer = f"Fel: {exc}"

        execute(
            "INSERT INTO messages(id,chat_id,role,content,created_at) VALUES(?,?,?,?,?)",
            (uid(), chat_id, "assistant", answer, now()),
        )
        execute("UPDATE chats SET updated_at=? WHERE id=?", (now(), chat_id))
        if chat.get("project_id"):
            execute("UPDATE projects SET updated_at=? WHERE id=?", (now(), chat["project_id"]))
    except Exception:
        for item in saved_images:
            storage_delete("chat_uploads", chat_id, item["stored_name"])
        execute("DELETE FROM messages WHERE id=?", (message_id,))
        raise

    return RedirectResponse(f"/chats/{chat_id}#latest", status_code=303)


@app.post("/chats/{chat_id}/rename")
def rename_chat(
    request: Request,
    chat_id: str,
    title: Annotated[str, Form(...)],
    csrf: Annotated[str, Form(...)],
    project_id: Annotated[str, Form()] = "",
):
    require_admin(request)
    verify_csrf(request, csrf)
    chat_or_404(chat_id)
    project_value = project_id.strip() or None
    if project_value:
        project_or_404(project_value)
    execute(
        "UPDATE chats SET title=?,project_id=?,updated_at=? WHERE id=?",
        (title.strip()[:120] or "Chatt", project_value, now(), chat_id),
    )
    return RedirectResponse(f"/chats/{chat_id}", status_code=303)


@app.post("/chats/{chat_id}/delete")
def delete_chat(request: Request, chat_id: str, csrf: Annotated[str, Form(...)]):
    require_admin(request)
    verify_csrf(request, csrf)
    chat_or_404(chat_id)
    storage_delete_prefix("chat_uploads", chat_id)
    execute("DELETE FROM chats WHERE id=?", (chat_id,))
    return RedirectResponse("/", status_code=303)
