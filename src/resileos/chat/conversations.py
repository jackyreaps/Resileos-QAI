"""Conversation threads for the public chat.

Threads are stored by API-key hash, then username, then hub. A digest in
RESILEOS_DEMO_KEY_SHA256 still caps distinct usernames on that one key.
The public chat page no longer embeds a shared key. Paid and personal
keys use the same username + hub layout, without that cap.
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

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

_REPO = Path(__file__).resolve().parents[3]
_DEMO_KEY_RE = re.compile(r'const DEMO_API_KEY = "([^"]+)"')
_USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,31}$")
_HUB_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")
_ROLES = {"user", "assistant"}
_MAX_MESSAGES = 200
_MAX_TEXT = 8000
_MAX_TITLE = 80

_demo_digest_cache: str | None = None
_store_lock = threading.Lock()


def store_path() -> Path:
    raw = os.getenv("RESILEOS_CONVERSATIONS_PATH", "").strip()
    if raw:
        return Path(raw)
    return _REPO / "data" / "conversations.json"


def demo_user_cap() -> int:
    raw = os.getenv("RESILEOS_DEMO_USER_CAP", "100").strip()
    try:
        cap = int(raw)
    except ValueError:
        return 100
    return cap if cap > 0 else 100


def demo_key_digest() -> str:
    """SHA-256 of the public demo key. Env override wins; the key is not logged."""
    override = os.getenv("RESILEOS_DEMO_KEY_SHA256", "").strip().lower()
    if len(override) == 64 and all(c in "0123456789abcdef" for c in override):
        return override
    global _demo_digest_cache
    if _demo_digest_cache is not None:
        return _demo_digest_cache
    digest = ""
    html_path = _REPO / "landing" / "public" / "chat.html"
    try:
        text = html_path.read_text(encoding="utf-8")
    except OSError:
        text = ""
    match = _DEMO_KEY_RE.search(text)
    if match:
        digest = hashlib.sha256(match.group(1).encode("utf-8")).hexdigest()
    _demo_digest_cache = digest
    return digest


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_username(value: str) -> str:
    name = (value or "").strip()
    if not _USERNAME_RE.fullmatch(name):
        raise ValueError(
            "username must be 2–32 characters: letters, digits, underscore, hyphen"
        )
    return name


def normalize_hub(value: str | None) -> str:
    hub = (value or "").strip() or "anon"
    if not _HUB_RE.fullmatch(hub):
        raise ValueError("hub_id must be 1–64 characters: letters, digits, _ . : -")
    return hub


def _clean_messages(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    if len(messages) > _MAX_MESSAGES:
        raise ValueError(f"a conversation can hold at most {_MAX_MESSAGES} messages")
    cleaned: list[dict[str, str]] = []
    for item in messages:
        if not isinstance(item, dict):
            raise ValueError("each message needs role and text")
        role = str(item.get("role") or "").strip().lower()
        if role not in _ROLES:
            raise ValueError("message role must be user or assistant")
        text = str(item.get("text") if item.get("text") is not None else item.get("content") or "")
        text = text.strip()
        if not text:
            continue
        if len(text) > _MAX_TEXT:
            raise ValueError(f"message text must be at most {_MAX_TEXT} characters")
        row: dict[str, str] = {"role": role, "text": text}
        status = item.get("status")
        if isinstance(status, str) and status.strip():
            row["status"] = status.strip()[:40]
        cleaned.append(row)
    if not cleaned:
        raise ValueError("a conversation needs at least one message")
    return cleaned


def _title_from(messages: list[dict[str, str]], explicit: str) -> str:
    title = " ".join((explicit or "").split())
    if not title:
        for message in messages:
            if message["role"] == "user" and message["text"]:
                title = " ".join(message["text"].split())
                break
    if not title:
        title = "Conversation"
    if len(title) > _MAX_TITLE:
        title = title[: _MAX_TITLE - 1].rstrip() + "…"
    return title


def _read() -> dict[str, Any]:
    path = store_path()
    if not path.exists():
        return {"owners": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"owners": {}}
    owners = data.get("owners") if isinstance(data, dict) else None
    if not isinstance(owners, dict):
        return {"owners": {}}
    return {"owners": owners}


def _write(data: dict[str, Any]) -> None:
    path = store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _owner_bucket(data: dict[str, Any], key_id: str) -> dict[str, Any]:
    owners = data["owners"]
    bucket = owners.get(key_id)
    if not isinstance(bucket, dict):
        bucket = {}
        owners[key_id] = bucket
    return bucket


def _hub_bucket(user_bucket: dict[str, Any], hub_id: str) -> dict[str, Any]:
    hubs = user_bucket.get("hubs")
    if not isinstance(hubs, dict):
        hubs = {}
        user_bucket["hubs"] = hubs
    hub = hubs.get(hub_id)
    if not isinstance(hub, dict):
        hub = {}
        hubs[hub_id] = hub
    return hub


def _public(record: dict[str, Any], *, with_messages: bool) -> dict[str, Any]:
    messages = record.get("messages") if isinstance(record.get("messages"), list) else []
    body: dict[str, Any] = {
        "id": record.get("id"),
        "username": record.get("username"),
        "hub_id": record.get("hub_id"),
        "title": record.get("title") or "Conversation",
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
        "message_count": len(messages),
    }
    if with_messages:
        body["messages"] = messages
    return body


def _find(bucket: dict[str, Any], username: str, hub_id: str, conversation_id: str) -> dict[str, Any] | None:
    user_bucket = bucket.get(username)
    if not isinstance(user_bucket, dict):
        return None
    hubs = user_bucket.get("hubs")
    if not isinstance(hubs, dict):
        return None
    hub = hubs.get(hub_id)
    if not isinstance(hub, dict):
        return None
    record = hub.get(conversation_id)
    if not isinstance(record, dict):
        return None
    return record


def _enforce_demo_cap(bucket: dict[str, Any], key_id: str, username: str) -> None:
    digest = demo_key_digest()
    if not digest or key_id != digest or username in bucket:
        return
    cap = demo_user_cap()
    if len(bucket) >= cap:
        raise HTTPException(
            status_code=429,
            detail=f"Shared demo key is limited to {cap} usernames.",
        )


class MessageIn(BaseModel):
    role: str
    text: str = ""
    content: str | None = None
    status: str | None = None


class ConversationIn(BaseModel):
    username: str
    hub_id: str = "anon"
    title: str = ""
    messages: list[MessageIn] = Field(default_factory=list)


def _payload(body: ConversationIn) -> tuple[str, str, str, list[dict[str, str]]]:
    try:
        username = normalize_username(body.username)
        hub_id = normalize_hub(body.hub_id)
        messages = _clean_messages([item.model_dump() for item in body.messages])
        title = _title_from(messages, body.title)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return username, hub_id, title, messages


def register_conversation_routes(app: FastAPI, key_id_dep: Callable[..., str]) -> None:
    """Mount create, list, get, and update. ``key_id_dep`` returns the key hash."""

    @app.post("/api/v1/conversations")
    def create_conversation(
        body: ConversationIn,
        key_id: str = Depends(key_id_dep),
    ) -> dict[str, Any]:
        username, hub_id, title, messages = _payload(body)
        now = _now()
        record = {
            "id": uuid.uuid4().hex,
            "username": username,
            "hub_id": hub_id,
            "title": title,
            "created_at": now,
            "updated_at": now,
            "messages": messages,
        }
        with _store_lock:
            data = _read()
            bucket = _owner_bucket(data, key_id)
            _enforce_demo_cap(bucket, key_id, username)
            user_bucket = bucket.get(username)
            if not isinstance(user_bucket, dict):
                user_bucket = {"hubs": {}}
                bucket[username] = user_bucket
            hub = _hub_bucket(user_bucket, hub_id)
            hub[record["id"]] = record
            _write(data)
        return _public(record, with_messages=True)

    @app.get("/api/v1/conversations")
    def list_conversations(
        username: str = Query(...),
        hub_id: str = Query("anon"),
        key_id: str = Depends(key_id_dep),
    ) -> dict[str, Any]:
        try:
            username = normalize_username(username)
            hub_id = normalize_hub(hub_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        with _store_lock:
            data = _read()
            bucket = data["owners"].get(key_id)
            hub: dict[str, Any] = {}
            if isinstance(bucket, dict):
                user_bucket = bucket.get(username)
                if isinstance(user_bucket, dict):
                    hubs = user_bucket.get("hubs")
                    if isinstance(hubs, dict) and isinstance(hubs.get(hub_id), dict):
                        hub = hubs[hub_id]
            records = [item for item in hub.values() if isinstance(item, dict)]
        records.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        return {
            "username": username,
            "hub_id": hub_id,
            "conversations": [_public(item, with_messages=False) for item in records],
        }

    @app.get("/api/v1/conversations/{conversation_id}")
    def get_conversation(
        conversation_id: str,
        username: str = Query(...),
        hub_id: str = Query("anon"),
        key_id: str = Depends(key_id_dep),
    ) -> dict[str, Any]:
        try:
            username = normalize_username(username)
            hub_id = normalize_hub(hub_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        with _store_lock:
            data = _read()
            bucket = data["owners"].get(key_id)
            record = _find(bucket, username, hub_id, conversation_id) if isinstance(bucket, dict) else None
        if record is None:
            raise HTTPException(status_code=404, detail="conversation not found")
        return _public(record, with_messages=True)

    @app.put("/api/v1/conversations/{conversation_id}")
    def update_conversation(
        conversation_id: str,
        body: ConversationIn,
        key_id: str = Depends(key_id_dep),
    ) -> dict[str, Any]:
        username, hub_id, title, messages = _payload(body)
        with _store_lock:
            data = _read()
            bucket = data["owners"].get(key_id)
            record = _find(bucket, username, hub_id, conversation_id) if isinstance(bucket, dict) else None
            if record is None:
                raise HTTPException(status_code=404, detail="conversation not found")
            record["title"] = title
            record["messages"] = messages
            record["updated_at"] = _now()
            record["username"] = username
            record["hub_id"] = hub_id
            _write(data)
            saved = dict(record)
        return _public(saved, with_messages=True)
