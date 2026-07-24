from __future__ import annotations

import base64
import hmac
import mimetypes
import os
import re
import secrets
import shutil
import sqlite3
import uuid
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.middleware.sessions import SessionMiddleware

APP_NAME = os.getenv("APP_NAME", "ProjectMind AI")
APP_PASSWORD = os.getenv("APP_PASSWORD", "").strip()
SESSION_SECRET = os.getenv("SESSION_SECRET", "").strip() or secrets.token_urlsafe(48)
SESSION_SECURE = os.getenv("SESSION_SECURE", "false").lower() == "true"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini").strip()
DATA_DIR = Path(os.getenv("DATA_DIR", "./storage")).resolve()
MAX_UPLOAD_MB = max(1, min(int(os.getenv("MAX_UPLOAD_MB", "50")), 500))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
MAX_CHAT_IMAGE_MB = max(1, min(int(os.getenv("MAX_CHAT_IMAGE_MB", "8")), 20))
MAX_CHAT_IMAGE_BYTES = MAX_CHAT_IMAGE_MB * 1024 * 1024
MAX_CHAT_IMAGES = max(1, min(int(os.getenv("MAX_CHAT_IMAGES", "4")), 8))

UPLOAD_DIR = DATA_DIR / "uploads"
VERSION_DIR = DATA_DIR / "versions"
CHAT_UPLOAD_DIR = DATA_DIR / "chat_uploads"
DB_PATH = DATA_DIR / "projectmind.db"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
VERSION_DIR.mkdir(parents=True, exist_ok=True)
CHAT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

BASE_DIR = Path(__file__).parent.resolve()
app = FastAPI(title=APP_NAME)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    https_only=SESSION_SECURE,
    same_site="lax",
    session_cookie="projectmind_session",
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

templates = Environment(
    loader=FileSystemLoader(BASE_DIR / "templates"),
    autoescape=select_autoescape(["html", "xml"]),
)

ALLOWED_EXTENSIONS = {
    ".zip", ".txt", ".md", ".json", ".csv", ".html", ".css", ".js", ".mjs", ".cjs",
    ".ts", ".tsx", ".jsx", ".py", ".java", ".xml", ".yaml", ".yml", ".toml",
    ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".docx", ".xlsx", ".pptx",
}


def uid() -> str:
    return uuid.uuid4().hex


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_filename(name: str) -> str:
    value = Path(name).name.strip()
    value = re.sub(r"[^A-Za-z0-9._()\- åäöÅÄÖ]", "_", value)
    value = re.sub(r"_+", "_", value)
    return value[:180] or "fil"


@contextmanager
def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                stack TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS project_files (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                original_name TEXT NOT NULL,
                stored_name TEXT NOT NULL,
                mime_type TEXT NOT NULL DEFAULT '',
                size_bytes INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS versions (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                version_label TEXT NOT NULL,
                comment TEXT NOT NULL DEFAULT '',
                original_name TEXT NOT NULL,
                stored_name TEXT NOT NULL,
                size_bytes INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS chats (
                id TEXT PRIMARY KEY,
                project_id TEXT,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user','assistant')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(chat_id) REFERENCES chats(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS chat_attachments (
                id TEXT PRIMARY KEY,
                message_id TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                original_name TEXT NOT NULL,
                stored_name TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE,
                FOREIGN KEY(chat_id) REFERENCES chats(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_files_project ON project_files(project_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_versions_project ON versions(project_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_chats_project ON chats(project_id, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id, created_at ASC);
            CREATE INDEX IF NOT EXISTS idx_chat_attachments_message ON chat_attachments(message_id, created_at ASC);
            CREATE INDEX IF NOT EXISTS idx_chat_attachments_chat ON chat_attachments(chat_id, created_at ASC);
            """
        )


init_db()


def fetchone(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    with db() as conn:
        row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def fetchall(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def execute(sql: str, params: tuple[Any, ...] = ()) -> None:
    with db() as conn:
        conn.execute(sql, params)


def render(request: Request, name: str, **context: Any) -> HTMLResponse:
    template = templates.get_template(name)
    base = {
        "request": request,
        "app_name": APP_NAME,
        "is_admin": bool(request.session.get("admin")),
        "csrf": request.session.get("csrf", ""),
    }
    base.update(context)
    return HTMLResponse(template.render(**base))


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


async def save_upload(upload: UploadFile, destination: Path) -> int:
    total = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as out:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                out.close()
                destination.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail=f"Filen är större än {MAX_UPLOAD_MB} MB.")
            out.write(chunk)
    await upload.close()
    return total


def project_context(project_id: str | None) -> str:
    if not project_id:
        return ""
    project = fetchone("SELECT * FROM projects WHERE id=?", (project_id,))
    if not project:
        return ""
    files = fetchall(
        "SELECT original_name,mime_type,size_bytes FROM project_files WHERE project_id=? ORDER BY created_at DESC LIMIT 100",
        (project_id,),
    )
    versions = fetchall(
        "SELECT version_label,comment,original_name,created_at FROM versions WHERE project_id=? ORDER BY created_at DESC LIMIT 50",
        (project_id,),
    )
    lines = [
        f"Projekt: {project['name']}",
        f"Status: {project['status']}",
        f"Stack: {project['stack']}",
        f"Beskrivning: {project['description']}",
        f"Anteckningar: {project['notes']}",
        "", "Filer:",
    ]
    lines.extend(f"- {f['original_name']} ({f['mime_type'] or 'okänd typ'}, {f['size_bytes']} bytes)" for f in files)
    lines.extend(["", "Versioner:"])
    lines.extend(f"- {v['version_label']}: {v['original_name']} — {v['comment']} ({v['created_at']})" for v in versions)
    return "\n".join(lines)


def extract_openai_text(payload: dict[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    parts: list[str] = []
    for item in payload.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and content.get("type") in {"output_text", "text"}:
                text = content.get("text")
                if isinstance(text, str):
                    parts.append(text)
    return "\n".join(parts).strip()



def image_to_data_url(record: dict[str, Any]) -> str:
    path = CHAT_UPLOAD_DIR / record["chat_id"] / record["stored_name"]
    if not path.exists():
        raise RuntimeError(f"Den bifogade bilden {record['original_name']} saknas på lagringen.")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{record['mime_type']};base64,{encoded}"


async def ask_ai(
    history: list[dict[str, str]],
    context: str,
    current_images: list[dict[str, Any]] | None = None,
) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY saknas. Lägg nyckeln som servermiljövariabel.")

    instructions = (
        "Du är ProjectMind AI, Ericas privata AI-assistent för utvecklingsprojekt. "
        "Svara praktiskt och tydligt på svenska när användaren skriver svenska. "
        "Använd projektkontexten när den finns men hitta inte på innehåll som saknas. "
        "När en bild bifogas ska du analysera det som faktiskt syns i bilden. "
        "Ge kompletta kodblock när kod efterfrågas."
    )
    if context:
        instructions += "\n\nAKTUELL PROJEKTKONTEXT:\n" + context[:50000]

    recent = [m for m in history[-30:] if m["role"] in {"user", "assistant"}]
    input_items: list[dict[str, Any]] = []

    for index, message in enumerate(recent):
        is_latest = index == len(recent) - 1
        if message["role"] == "user" and is_latest and current_images:
            content_items: list[dict[str, Any]] = []
            text = message["content"].strip()

            content_items.append({
                "type": "input_text",
                "text": text or "Analysera den eller de bifogade bilderna i relation till mitt projekt.",
            })

            for image in current_images:
                content_items.append({
                    "type": "input_image",
                    "image_url": image_to_data_url(image),
                    "detail": "auto",
                })

            input_items.append({"role": "user", "content": content_items})
        else:
            input_items.append({
                "role": message["role"],
                "content": message["content"],
            })

    payload = {
        "model": OPENAI_MODEL,
        "instructions": instructions,
        "input": input_items,
        "store": False,
    }

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    timeout = httpx.Timeout(connect=20.0, read=180.0, write=60.0, pool=20.0)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                "https://api.openai.com/v1/responses",
                headers=headers,
                json=payload,
            )
    except httpx.TimeoutException as exc:
        raise RuntimeError("AI-anropet tog för lång tid. Försök igen.") from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"Kunde inte ansluta till OpenAI API: {exc}") from exc

    if response.status_code >= 400:
        try:
            data = response.json()
            message = (data.get("error") or {}).get("message") or response.text[:500]
        except Exception:
            message = response.text[:500]
        raise RuntimeError(f"OpenAI API-fel ({response.status_code}): {message}")

    answer = extract_openai_text(response.json())
    if not answer:
        raise RuntimeError("AI-svaret saknade text.")
    return answer


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/login")
def login_page(request: Request):
    if request.session.get("admin"):
        return RedirectResponse("/", status_code=303)
    return render(request, "login.html", error="")


@app.post("/login")
def login(request: Request, password: Annotated[str, Form(...)]):
    if not APP_PASSWORD:
        return render(request, "login.html", error="APP_PASSWORD saknas i serverns miljövariabler.")
    if not hmac.compare_digest(password, APP_PASSWORD):
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
    if not request.session.get("admin"):
        return RedirectResponse("/login", status_code=303)
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
        SELECT c.*,p.name AS project_name FROM chats c
        LEFT JOIN projects p ON p.id=c.project_id
        ORDER BY c.updated_at DESC LIMIT 20
        """
    )
    return render(request, "dashboard.html", projects=projects, chats=chats)


@app.post("/projects")
def create_project(
    request: Request,
    name: Annotated[str, Form(...)],
    csrf: Annotated[str, Form(...)],
    description: Annotated[str, Form()] = "",
    status: Annotated[str, Form()] = "active",
    stack: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
):
    require_admin(request)
    verify_csrf(request, csrf)
    project_id = uid()
    timestamp = now()
    execute(
        "INSERT INTO projects(id,name,description,status,stack,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
        (project_id, name.strip()[:120] or "Nytt projekt", description.strip(), status.strip()[:40] or "active", stack.strip(), notes.strip(), timestamp, timestamp),
    )
    return RedirectResponse(f"/projects/{project_id}", status_code=303)


@app.get("/projects/{project_id}")
def project_page(request: Request, project_id: str):
    require_admin(request)
    project = project_or_404(project_id)
    files = fetchall("SELECT * FROM project_files WHERE project_id=? ORDER BY created_at DESC", (project_id,))
    versions = fetchall("SELECT * FROM versions WHERE project_id=? ORDER BY created_at DESC", (project_id,))
    chats = fetchall("SELECT * FROM chats WHERE project_id=? ORDER BY updated_at DESC", (project_id,))
    return render(request, "project.html", project=project, files=files, versions=versions, chats=chats, max_upload_mb=MAX_UPLOAD_MB)


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
        (name.strip()[:120] or "Projekt", description.strip(), status.strip()[:40] or "active", stack.strip(), notes.strip(), now(), project_id),
    )
    return RedirectResponse(f"/projects/{project_id}", status_code=303)


@app.post("/projects/{project_id}/delete")
def delete_project(request: Request, project_id: str, csrf: Annotated[str, Form(...)]):
    require_admin(request)
    verify_csrf(request, csrf)
    project_or_404(project_id)
    chat_ids = fetchall("SELECT id FROM chats WHERE project_id=?", (project_id,))
    for item in chat_ids:
        shutil.rmtree(CHAT_UPLOAD_DIR / item["id"], ignore_errors=True)
    shutil.rmtree(UPLOAD_DIR / project_id, ignore_errors=True)
    shutil.rmtree(VERSION_DIR / project_id, ignore_errors=True)
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
    ext = Path(original).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Filtypen {ext or '(utan ändelse)'} är inte tillåten.")
    stored = f"{uid()}_{original}"
    destination = UPLOAD_DIR / project_id / stored
    size = await save_upload(upload, destination)
    mime = upload.content_type or mimetypes.guess_type(original)[0] or "application/octet-stream"
    execute(
        "INSERT INTO project_files(id,project_id,original_name,stored_name,mime_type,size_bytes,created_at) VALUES(?,?,?,?,?,?,?)",
        (uid(), project_id, original, stored, mime, size, now()),
    )
    execute("UPDATE projects SET updated_at=? WHERE id=?", (now(), project_id))
    return RedirectResponse(f"/projects/{project_id}", status_code=303)


@app.get("/files/{file_id}/download")
def download_file(request: Request, file_id: str):
    require_admin(request)
    record = fetchone("SELECT * FROM project_files WHERE id=?", (file_id,))
    if not record:
        raise HTTPException(status_code=404, detail="Filen hittades inte.")
    path = UPLOAD_DIR / record["project_id"] / record["stored_name"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Filen saknas på lagringen.")
    return FileResponse(path, filename=record["original_name"], media_type=record["mime_type"] or "application/octet-stream")


@app.post("/files/{file_id}/delete")
def delete_file(request: Request, file_id: str, csrf: Annotated[str, Form(...)]):
    require_admin(request)
    verify_csrf(request, csrf)
    record = fetchone("SELECT * FROM project_files WHERE id=?", (file_id,))
    if not record:
        raise HTTPException(status_code=404, detail="Filen hittades inte.")
    (UPLOAD_DIR / record["project_id"] / record["stored_name"]).unlink(missing_ok=True)
    execute("DELETE FROM project_files WHERE id=?", (file_id,))
    return RedirectResponse(f"/projects/{record['project_id']}", status_code=303)


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
    stored = f"{uid()}_{original}"
    destination = VERSION_DIR / project_id / stored
    size = await save_upload(upload, destination)
    try:
        with zipfile.ZipFile(destination) as zf:
            for info in zf.infolist():
                candidate = Path(info.filename)
                if candidate.is_absolute() or ".." in candidate.parts:
                    destination.unlink(missing_ok=True)
                    raise HTTPException(status_code=400, detail="ZIP-filen innehåller en osäker sökväg.")
    except zipfile.BadZipFile as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Ogiltig ZIP-fil.") from exc
    execute(
        "INSERT INTO versions(id,project_id,version_label,comment,original_name,stored_name,size_bytes,created_at) VALUES(?,?,?,?,?,?,?,?)",
        (uid(), project_id, version_label.strip()[:80] or "Version", comment.strip(), original, stored, size, now()),
    )
    execute("UPDATE projects SET updated_at=? WHERE id=?", (now(), project_id))
    return RedirectResponse(f"/projects/{project_id}", status_code=303)


@app.get("/versions/{version_id}/download")
def download_version(request: Request, version_id: str):
    require_admin(request)
    record = fetchone("SELECT * FROM versions WHERE id=?", (version_id,))
    if not record:
        raise HTTPException(status_code=404, detail="Versionen hittades inte.")
    path = VERSION_DIR / record["project_id"] / record["stored_name"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="ZIP-filen saknas på lagringen.")
    return FileResponse(path, filename=record["original_name"], media_type="application/zip")


@app.post("/versions/{version_id}/delete")
def delete_version(request: Request, version_id: str, csrf: Annotated[str, Form(...)]):
    require_admin(request)
    verify_csrf(request, csrf)
    record = fetchone("SELECT * FROM versions WHERE id=?", (version_id,))
    if not record:
        raise HTTPException(status_code=404, detail="Versionen hittades inte.")
    (VERSION_DIR / record["project_id"] / record["stored_name"]).unlink(missing_ok=True)
    execute("DELETE FROM versions WHERE id=?", (version_id,))
    return RedirectResponse(f"/projects/{record['project_id']}", status_code=303)


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
    project = fetchone(
        "SELECT * FROM projects WHERE id=?",
        (chat["project_id"],),
    ) if chat["project_id"] else None

    messages = fetchall(
        "SELECT * FROM messages WHERE chat_id=? ORDER BY created_at ASC",
        (chat_id,),
    )
    attachments = fetchall(
        "SELECT * FROM chat_attachments WHERE chat_id=? ORDER BY created_at ASC",
        (chat_id,),
    )

    attachments_by_message: dict[str, list[dict[str, Any]]] = {}
    for item in attachments:
        attachments_by_message.setdefault(item["message_id"], []).append(item)

    projects = fetchall("SELECT id,name FROM projects ORDER BY updated_at DESC")

    return render(
        request,
        "chat.html",
        chat=chat,
        project=project,
        messages=messages,
        attachments_by_message=attachments_by_message,
        projects=projects,
        max_chat_image_mb=MAX_CHAT_IMAGE_MB,
        max_chat_images=MAX_CHAT_IMAGES,
    )


@app.get("/chat-images/{attachment_id}")
def chat_image(request: Request, attachment_id: str):
    require_admin(request)
    record = fetchone(
        "SELECT * FROM chat_attachments WHERE id=?",
        (attachment_id,),
    )
    if not record:
        raise HTTPException(status_code=404, detail="Bilden hittades inte.")

    path = CHAT_UPLOAD_DIR / record["chat_id"] / record["stored_name"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Bildfilen saknas på lagringen.")

    return FileResponse(
        path,
        filename=record["original_name"],
        media_type=record["mime_type"],
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

    if len(real_images) > MAX_CHAT_IMAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Du kan bifoga högst {MAX_CHAT_IMAGES} bilder per meddelande.",
        )

    allowed_image_types = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }

    message_id = uid()
    display_text = user_text or "📎 Bild bifogad"

    execute(
        "INSERT INTO messages(id,chat_id,role,content,created_at) VALUES(?,?,?,?,?)",
        (message_id, chat_id, "user", display_text, now()),
    )

    saved_images: list[dict[str, Any]] = []

    try:
        for upload in real_images:
            content_type = (upload.content_type or "").lower()
            original = safe_filename(upload.filename or "bild.png")
            ext = Path(original).suffix.lower()

            if content_type not in allowed_image_types:
                raise HTTPException(
                    status_code=400,
                    detail="Chatten accepterar PNG, JPG/JPEG, WEBP och GIF.",
                )

            expected_ext = allowed_image_types[content_type]
            valid_exts = {expected_ext}
            if expected_ext == ".jpg":
                valid_exts.add(".jpeg")
            if ext not in valid_exts:
                original = f"{Path(original).stem}{expected_ext}"

            stored = f"{uid()}_{original}"
            destination = CHAT_UPLOAD_DIR / chat_id / stored
            destination.parent.mkdir(parents=True, exist_ok=True)

            total = 0
            with destination.open("wb") as out:
                while True:
                    chunk = await upload.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_CHAT_IMAGE_BYTES:
                        out.close()
                        destination.unlink(missing_ok=True)
                        raise HTTPException(
                            status_code=413,
                            detail=f"En chattbild får vara högst {MAX_CHAT_IMAGE_MB} MB.",
                        )
                    out.write(chunk)

            await upload.close()

            attachment_id = uid()
            execute(
                """
                INSERT INTO chat_attachments(
                    id,message_id,chat_id,original_name,stored_name,mime_type,size_bytes,created_at
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    attachment_id,
                    message_id,
                    chat_id,
                    original,
                    stored,
                    content_type,
                    total,
                    now(),
                ),
            )

            saved_images.append({
                "id": attachment_id,
                "message_id": message_id,
                "chat_id": chat_id,
                "original_name": original,
                "stored_name": stored,
                "mime_type": content_type,
                "size_bytes": total,
            })

        history = fetchall(
            "SELECT role,content FROM messages WHERE chat_id=? ORDER BY created_at ASC",
            (chat_id,),
        )

        try:
            answer = await ask_ai(
                history,
                project_context(chat["project_id"]),
                current_images=saved_images,
            )
        except RuntimeError as exc:
            answer = f"Fel: {exc}"

        execute(
            "INSERT INTO messages(id,chat_id,role,content,created_at) VALUES(?,?,?,?,?)",
            (uid(), chat_id, "assistant", answer, now()),
        )
        execute("UPDATE chats SET updated_at=? WHERE id=?", (now(), chat_id))

    except Exception:
        for item in saved_images:
            (CHAT_UPLOAD_DIR / chat_id / item["stored_name"]).unlink(missing_ok=True)
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
    shutil.rmtree(CHAT_UPLOAD_DIR / chat_id, ignore_errors=True)
    execute("DELETE FROM chats WHERE id=?", (chat_id,))
    return RedirectResponse("/", status_code=303)
