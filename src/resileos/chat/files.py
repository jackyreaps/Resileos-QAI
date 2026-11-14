"""Per-account Files: upload, list, download, delete.

Files are stored by API-key hash (the same owner id as conversations), on
local disk under RESILEOS_FILES_DIR (default data/files). They are private
to the account. Nothing here learns, perceives into the store, or moves a
file to a shared or world tier. Anonymous trial visitors can't store files.

Limits (env overrides): RESILEOS_FILE_MAX_BYTES (10 MB),
RESILEOS_FILES_MAX_TOTAL (100 MB per account), RESILEOS_FILES_MAX_COUNT (200).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response

_REPO = Path(__file__).resolve().parents[3]
_ID = re.compile(r"^[a-f0-9]{32}$")
_LOCK = threading.Lock()

# extension -> (kind, served content type)
TYPES: dict[str, tuple[str, str]] = {
    ".png": ("image", "image/png"),
    ".jpg": ("image", "image/jpeg"),
    ".jpeg": ("image", "image/jpeg"),
    ".webp": ("image", "image/webp"),
    ".gif": ("image", "image/gif"),
    ".mp4": ("clip", "video/mp4"),
    ".webm": ("clip", "video/webm"),
    ".mov": ("clip", "video/quicktime"),
    ".txt": ("text", "text/plain; charset=utf-8"),
    ".md": ("text", "text/plain; charset=utf-8"),
    ".csv": ("text", "text/plain; charset=utf-8"),
    ".json": ("text", "text/plain; charset=utf-8"),
    ".py": ("text", "text/plain; charset=utf-8"),
    ".lean": ("lean", "text/plain; charset=utf-8"),
}
_MAGIC = {
    ".png": [b"\x89PNG\r\n\x1a\n"],
    ".jpg": [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    ".gif": [b"GIF87a", b"GIF89a"],
    ".webp": [b"RIFF"],
    ".webm": [b"\x1a\x45\xdf\xa3"],
}


def _int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def limits() -> dict[str, int]:
    return {
        "max_bytes": _int_env("RESILEOS_FILE_MAX_BYTES", 10 * 1024 * 1024),
        "max_total": _int_env("RESILEOS_FILES_MAX_TOTAL", 100 * 1024 * 1024),
        "max_count": _int_env("RESILEOS_FILES_MAX_COUNT", 200),
    }


def files_root() -> Path:
    raw = os.getenv("RESILEOS_FILES_DIR", "").strip()
    return Path(raw) if raw else _REPO / "data" / "files"


def _owner_dir(key_id: str) -> Path:
    return files_root() / hashlib.sha256(key_id.encode("utf-8")).hexdigest()[:32]


def _index(owner: Path) -> list[dict[str, Any]]:
    path = owner / "index.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def _write_index(owner: Path, rows: list[dict[str, Any]]) -> None:
    owner.mkdir(parents=True, exist_ok=True)
    tmp = owner / "index.json.tmp"
    tmp.write_text(json.dumps(rows), encoding="utf-8")
    tmp.replace(owner / "index.json")


def _clean_name(name: str) -> str:
    base = os.path.basename(str(name or "file")).strip().replace("\x00", "")
    base = re.sub(r"[\r\n\t\"\\/]", "_", base)[:120]
    return base or "file"


def check_type(name: str, content: bytes) -> tuple[str, str, str]:
    ext = os.path.splitext(name)[1].lower()
    if ext not in TYPES:
        raise HTTPException(415, "That file type isn't supported. Use a picture, a short video, or a text, CSV, JSON, Python or Lean file.")
    kind, served = TYPES[ext]
    magics = _MAGIC.get(ext)
    if magics and not any(content.startswith(m) for m in magics):
        raise HTTPException(415, "That file doesn't look like a real " + ext[1:].upper() + " file.")
    if ext in {".mp4", ".mov"} and content[4:8] != b"ftyp":
        raise HTTPException(415, "That file doesn't look like a real video file.")
    if kind in {"text", "lean"}:
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(415, "Text files must be UTF-8.") from exc
    return ext, kind, served


def _public(row: dict[str, Any]) -> dict[str, Any]:
    return {k: row[k] for k in ("id", "name", "kind", "type", "size", "created_at") if k in row}


def _require_account(key_id: str) -> None:
    if not key_id or key_id.startswith("trial:"):
        raise HTTPException(401, "Sign in to keep files.")


def register_file_routes(app: FastAPI, key_id_dep: Callable[..., str]) -> None:
    @app.get("/api/v1/files")
    def list_files(key_id: str = Depends(key_id_dep)) -> dict[str, Any]:
        _require_account(key_id)
        rows = _index(_owner_dir(key_id))
        rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        return {"files": [_public(r) for r in rows], "used": sum(int(r.get("size") or 0) for r in rows), "limits": limits()}

    @app.post("/api/v1/files")
    async def upload_file(file: UploadFile = File(...), key_id: str = Depends(key_id_dep)) -> dict[str, Any]:
        _require_account(key_id)
        lim = limits()
        content = await file.read(lim["max_bytes"] + 1)
        if len(content) > lim["max_bytes"]:
            raise HTTPException(413, f"Files can be up to {lim['max_bytes'] // (1024 * 1024)} MB.")
        if not content:
            raise HTTPException(400, "That file is empty.")
        name = _clean_name(file.filename or "file")
        ext, kind, served = check_type(name, content)
        owner = _owner_dir(key_id)
        with _LOCK:
            rows = _index(owner)
            if len(rows) >= lim["max_count"]:
                raise HTTPException(413, f"You can keep up to {lim['max_count']} files. Delete some first.")
            if sum(int(r.get("size") or 0) for r in rows) + len(content) > lim["max_total"]:
                raise HTTPException(413, "Your Files space is full. Delete some files first.")
            fid = uuid.uuid4().hex
            owner.mkdir(parents=True, exist_ok=True)
            (owner / (fid + ".bin")).write_bytes(content)
            row = {
                "id": fid,
                "name": name,
                "kind": kind,
                "type": served.split(";")[0],
                "size": len(content),
                "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "tier": "personal",
            }
            rows.append(row)
            _write_index(owner, rows)
        return _public(row)

    @app.get("/api/v1/files/{file_id}")
    def download_file(file_id: str, key_id: str = Depends(key_id_dep)) -> Response:
        _require_account(key_id)
        if not _ID.match(file_id):
            raise HTTPException(404, "File not found.")
        owner = _owner_dir(key_id)
        row = next((r for r in _index(owner) if r.get("id") == file_id), None)
        blob = owner / (file_id + ".bin")
        if row is None or not blob.exists():
            raise HTTPException(404, "File not found.")
        served = TYPES.get(os.path.splitext(row["name"])[1].lower(), ("file", "application/octet-stream"))[1]
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", row["name"])
        return Response(
            content=blob.read_bytes(),
            media_type=served,
            headers={
                "Content-Disposition": f'attachment; filename="{safe}"',
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "private, no-store",
            },
        )

    @app.delete("/api/v1/files/{file_id}")
    def delete_file(file_id: str, key_id: str = Depends(key_id_dep)) -> dict[str, Any]:
        _require_account(key_id)
        if not _ID.match(file_id):
            raise HTTPException(404, "File not found.")
        owner = _owner_dir(key_id)
        with _LOCK:
            rows = _index(owner)
            keep = [r for r in rows if r.get("id") != file_id]
            if len(keep) == len(rows):
                raise HTTPException(404, "File not found.")
            _write_index(owner, keep)
            blob = owner / (file_id + ".bin")
            if blob.exists():
                blob.unlink()
        return {"deleted": True, "id": file_id}
