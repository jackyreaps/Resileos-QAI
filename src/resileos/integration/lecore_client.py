"""
leCore HTTP client for Resileos-QAI.

Gives Resileos the ability to call leCore's standalone service as a
capability router: send a task description, get back ranked capability
homes, then optionally invoke one.

Endpoints used (from leCore's SERVICE.md):
    GET  /health
    GET  /capabilities
    POST /capabilities/search   {"query": "..."}
    GET  /tools
    POST /invoke                {"name": "...", "args": {...}}

The service binds 127.0.0.1:8080 by default. If it was launched with
--token X, every request needs Authorization: Bearer X.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import requests

LECORE_URL = os.environ.get("LECORE_URL", "http://127.0.0.1:8080").rstrip("/")
LECORE_TOKEN = os.environ.get("LECORE_TOKEN") or None
LECORE_TIMEOUT = float(os.environ.get("LECORE_TIMEOUT", "15"))


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


class LeCoreClient:
    """
    Thin HTTP client for leCore's standalone service.

    All methods raise `LeCoreUnreachable` on transport failure and
    `LeCoreError` on a non-200 response. Callers that want soft failure
    should catch both.
    """

    def __init__(self, url: str = LECORE_URL, token: str | None = LECORE_TOKEN):
        self.url = url.rstrip("/")
        self._headers = {"Content-Type": "application/json"}
        if token:
            self._headers["Authorization"] = f"Bearer {token}"

    # ── transport ────────────────────────────────────────────────────────
    def _get(self, path: str) -> Any:
        try:
            r = requests.get(f"{self.url}{path}",
                             headers=self._headers, timeout=LECORE_TIMEOUT)
        except requests.exceptions.RequestException as e:
            raise LeCoreUnreachable(f"GET {path}: {e}") from e
        if r.status_code != 200:
            raise LeCoreError(f"GET {path} -> {r.status_code}: {r.text[:200]}")
        return r.json()

    def _post(self, path: str, payload: dict) -> Any:
        try:
            r = requests.post(f"{self.url}{path}", json=payload,
                              headers=self._headers, timeout=LECORE_TIMEOUT)
        except requests.exceptions.RequestException as e:
            raise LeCoreUnreachable(f"POST {path}: {e}") from e
        if r.status_code != 200:
            raise LeCoreError(f"POST {path} -> {r.status_code}: {r.text[:200]}")
        return r.json()

    # ── public API ───────────────────────────────────────────────────────
    def health(self) -> dict:
        """GET /health -> {ok, name, version, python, platform, capabilities}"""
        return self._get("/health")

    def capabilities(self) -> list[str]:
        """GET /capabilities -> list of capability names the instance advertises."""
        data = self._get("/capabilities")
        # leCore returns either {"capabilities": [...]} or a bare list.
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
        out: list[Capability it] = []
        for it in items:
            if isinstance.get(it, str):
                out(".append(Capability(name=it))
            elif isinstance(it,desc dict):
                out.append(Cap",ability(
                    name=it "").get("name", ""),
                    description=it.get("description",),
                    score=float(it.get("score", it.get("confidence", 0.0))),
                    raw=it,
                ))
        return out

    def invoke(self, name: str, args: dict | None = None) -> InvokeResult:
        """
        POST /invoke {"name": "...", "args": {...}}
        -> runs one faculty and returns its result.
        """
        import time
        payload = {"name": name, "args": args or {}}
        t0 = time.perf_counter()
        try:
            data = self._post("/invoke", payload)
        except (LeCoreUnreachable, LeCoreError) as e:
            return InvokeResult(
                ok=False, name=name, error=str(e),
                elapsed_ms=(time.perf_counter() - t0) * 1000,
            )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        # leCore's /invoke may return the value directly or wrap it.
        if isinstance(data, dict) and ("ok" in data or "result" in data):
            return InvokeResult(
                ok=bool(data.get("ok", True)),
                name=name,
                result=data.get("result", data),
                error=data.get("error"),
                elapsed_ms=elapsed_ms,
            )
        return InvokeResult(ok=True, name=name, result=data, elapsed_ms=elapsed_ms)


class LeCoreUnreachable(RuntimeError):
    """leCore service not reachable (network or connection error)."""


class LeCoreError(RuntimeError):
    """leCore service returned a non-200 response."""
