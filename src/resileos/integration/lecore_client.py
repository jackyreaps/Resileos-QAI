"""
leCore HTTP client for Resileos-QAI.

Gives Resileos the ability to call leCore's standalone service as a
capability router: send a task description, get back ranked capability
homes, then optionally invoke one.

Endpoints (from leCore's SERVICE.md):
    GET  /health
    GET  /capabilities
    POST /capabilities/search   {"query": "..."}
    GET  /tools
    POST /invoke                {"name": "...", "args": {...}}

The service binds 127.0.0.1:8080 by default. If it was launched with
--token X, every request needs Authorization: Bearer X.

Configuration via environment:
    LECORE_URL      default http://127.0.0.1:8080
    LECORE_TOKEN    optional bearer token
    LECORE_TIMEOUT  seconds, default 15
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

import requests

LECORE_URL = os.environ.get("LECORE_URL", "http://127.0.0.1:8080").rstrip("/")
LECORE_TOKEN = os.environ.get("LECORE_TOKEN") or None
LECORE_TIMEOUT = float(os.environ.get("LECORE_TIMEOUT", "15"))


# ── errors ──────────────────────────────────────────────────────────────
class LeCoreUnreachable(RuntimeError):
    """leCore service not reachable (network or connection error)."""


class LeCoreError(RuntimeError):
    """leCore service returned a non-200 response."""


# ── result types ────────────────────────────────────────────────────────
@dataclass
class Capability:
    name: str
    description: str = ""
    score: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class InvokeResult:
    ok: bool
    name: str
    result: Any = None
    error: str | None = None
    elapsed_ms: float = 0.0


# ── client ──────────────────────────────────────────────────────────────
class LeCoreClient:
    """
    Thin HTTP client for leCore's standalone service.

    All methods raise LeCoreUnreachable on transport failure and
    LeCoreError on a non-200 response, except `invoke`, which returns
    InvokeResult(ok=False, ...) so it can be used as a soft capability.
    """

    def __init__(self, url: str = LECORE_URL, token: str | None = LECORE_TOKEN):
        self.url = url.rstrip("/")
        self._headers = {"Content-Type": "application/json"}
        if token:
            self._headers["Authorization"] = f"Bearer {token}"

    # ── transport ───────────────────────────────────────────────────────
    def _get(self, path: str) -> Any:
        try:
            r = requests.get(
                f"{self.url}{path}",
                headers=self._headers,
                timeout=LECORE_TIMEOUT,
            )
        except requests.exceptions.RequestException as e:
            raise LeCoreUnreachable(f"GET {path}: {e}") from e
        if r.status_code != 200:
            raise LeCoreError(f"GET {path} -> {r.status_code}: {r.text[:200]}")
        return r.json()

    def _post(self, path: str, payload: dict) -> Any:
        try:
            r = requests.post(
                f"{self.url}{path}",
                json=payload,
                headers=self._headers,
                timeout=LECORE_TIMEOUT,
            )
        except requests.exceptions.RequestException as e:
            raise LeCoreUnreachable(f"POST {path}: {e}") from e
        if r.status_code != 200:
            raise LeCoreError(f"POST {path} -> {r.status_code}: {r.text[:200]}")
        return r.json()

    # ── public API ──────────────────────────────────────────────────────
    def health(self) -> dict:
        """GET /health -> {ok, name, version, python, platform, capabilities}."""
        return self._get("/health")

    def capabilities(self) -> list[str]:
        """GET /capabilities -> list of advertised capability names."""
        data = self._get("/capabilities")
        if isinstance(data, dict):
            return list(data.get("capabilities", data.get("names", [])))
        return list(data)

    def tools(self) -> list[dict]:
        """GET /tools -> manifest of {name, description, params} per faculty."""
        data = self._get("/tools")
        if isinstance(data, dict):
            return list(data.get("tools", []))
        return list(data)

    def search(self, query: str) -> list[Capability]:
        """
        POST /capabilities/search {"query": "..."}
        -> ranked capability homes matching the query.
        """
        data = self._post("/capabilities/search", {"query": query})
        items = data if isinstance(data, list) else data.get("results", [])
        out: list[Capability] = []
        for it in items:
            if isinstance(it, str):
                out.append(Capability(name=it))
            elif isinstance(it, dict):
                out.append(Capability(
                    name=it.get("name", ""),
                    description=it.get("description", it.get("desc", "")),
                    score=float(it.get("score", it.get("confidence", 0.0))),
                    raw=it,
                ))
        return out

    def invoke(self, name: str, args: dict | None = None) -> InvokeResult:
        """
        POST /invoke {"name": "...", "args": {...}}
        -> run one faculty. Soft-fails: returns InvokeResult(ok=False, ...)
        on transport failure, so callers do not need try/except.
        """
        payload = {"name": name, "args": args or {}}
        t0 = time.perf_counter()
        try:
            data = self._post("/invoke", payload)
        except (LeCoreUnreachable, LeCoreError) as e:
            return InvokeResult(
                ok=False,
                name=name,
                error=str(e),
                elapsed_ms=(time.perf_counter() - t0) * 1000,
            )
        elapsed_ms = (time.perf_counter() - t0) * 1000

        if isinstance(data, dict) and ("ok" in data or "result" in data):
            return InvokeResult(
                ok=bool(data.get("ok", True)),
                name=name,
                result=data.get("result", data),
                error=data.get("error"),
                elapsed_ms=elapsed_ms,
            )
        return InvokeResult(ok=True, name=name, result=data, elapsed_ms=elapsed_ms)

    def is_available(self) -> bool:
        """Soft check: True if /health responds 200. Never raises."""
        try:
            self.health()
            return True
        except (LeCoreUnreachable, LeCoreError):
            return False
