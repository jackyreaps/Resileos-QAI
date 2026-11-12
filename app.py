"""
FastAPI backend for Resileos-QAI.
...
(Existing docstring)
...
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Optional

import numpy as np
import torch
from fastapi import Depends, FastAPI, HTTPException, Query, UploadFile, File, Form
from PIL import Image
import io

from resileos.ui.shared_state import init_shared
from resileos.ui.query_scale import with_scale
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field
from starlette.status import HTTP_403_FORBIDDEN

ROOT = Path(__file__).resolve().parent
for p in (ROOT, ROOT / "src", ROOT / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from resileos.answer import (  # noqa: E402
    AnswerBackend,
    AnswerContext,
    StructuredBackend,
    context_from_answer,
    encode_gate,
    encode_question,
    frame_index,
    gbx_bypass_recurrent,
    list_backends,
    list_tool_schemas,
    openai_tools,
    select_backend,
)
from resileos.answer.policy import (  # noqa: E402
    derive_frame,
    prefer_child,
)
from resileos.integration.lecore_client import (  # noqa: E402
    LeCoreClient, LeCoreUnreachable, LeCoreError,
)
from resileos.substrate.geometry import LowRankMetricHead  # noqa: E402
from resileos.substrate.reduction import (  # noqa: E402
    VerifiableFEPReductionHead,
    simulate_axiom_d,
)
from resileos.titanos.query import (  # noqa: E402
    TitanosQueryEngine,
    QuerySyntaxError,
    QueryBindingError,
)
from resileos.substrate.agency import AgencyGroup  # noqa: E402
from resileos.titanos.zeus import (  # noqa: E402
    make_zeus_handler,
    run_zeus_query,
)
from resileos.kin.wiring import wire_kin  # noqa: E402
from resileos.answer.agent_loop import run_agent_chat  # <--- IMPORTED

# ── Harness tool surface ───────────────────────────────────────────────
from resileos.harness.surface import (  # noqa: E402
    ALWAYS_VISIBLE_TOOLS as HARNESS_TOOLS,
    search_tool_surface,
)

from titanos import Answer, Titanos, TitanosConfig  # noqa: E402

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("resileos.api")

app = FastAPI(title="Resileos-QAI")
init_shared()

STATE_FILE = ROOT / "titanos_live_state.json"
SEED_FILE = ROOT / "configs" / "titanos-facts.json"

SUBSTRATE_STATE_PATH = Path(
    os.getenv(
        "RESILEOS_SUBSTRATE_STATE",
        str(ROOT / "data" / "substrate_state.pt"),
    )
)

_substrate_lock = threading.Lock()


# ═══════════════════════════════════════════════════════════════════════════
# API key auth (fail-closed)
# ═══════════════════════════════════════════════════════════════════════════
_API_KEY_NAME = "X-API-Key"
_api_key_header = APIKeyHeader(name=_API_KEY_NAME, auto_error=False)
_KEYS_PATH = Path(
    os.getenv("API_KEYS_PATH", str(ROOT / "configs" / "api_keys.json"))
)
_AUTH_BYPASS = os.getenv("RESILEOS_AUTH_BYPASS", "0") == "1"

# Static site (Cloudflare Pages). RESILEOS_CORS_ORIGINS replaces this list.
DEFAULT_CORS_ORIGINS = (
    "https://resileosai.fun",
    "https://www.resileosai.fun",
)


def configured_cors_origins() -> list[str]:
    """Origins for browser calls. Empty env keeps the two production sites."""
    raw = os.getenv("RESILEOS_CORS_ORIGINS", "").strip()
    if not raw:
        return list(DEFAULT_CORS_ORIGINS)
    return [part.strip() for part in raw.split(",") if part.strip()]


def _hash_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_hashed_keys() -> dict[str, dict]:
    merged: dict[str, dict] = {}
    if _KEYS_PATH.exists():
        try:
            merged.update(json.loads(_KEYS_PATH.read_text(encoding="utf-8")))
        except Exception as e:
            log.warning("API key file unreadable (%s): %s", _KEYS_PATH, e)
    raw_env = os.getenv("RESILEOS_API_KEYS", "").strip()
    if raw_env:
        try:
            for key, record in json.loads(raw_env).items():
                is_hex = len(key) == 64 and all(
                    c in "0123456789abcdef" for c in key.lower()
                )
                merged[key if is_hex else _hash_key(key)] = record
        except Exception as e:
            log.warning("RESILEOS_API_KEYS is not valid JSON: %s", e)
    legacy = os.getenv("RESILEOS_API_KEY", "").strip()
    if legacy:
        merged.setdefault(
            _hash_key(legacy),
            {"name": "legacy", "tier": "enterprise", "quota": 0},
        )
    return merged


def _configured_key_count() -> int:
    return len(_load_hashed_keys())


async def verify_api_key(
    api_key: str | None = Depends(_api_key_header),
) -> None:
    if _AUTH_BYPASS:
        return
    keys = _load_hashed_keys()
    if not keys:
        raise HTTPException(
            status_code=503,
            detail=(
                "No API keys configured. Set API_KEYS_PATH, RESILEOS_API_KEYS, "
                "or RESILEOS_API_KEY. Local dev only: RESILEOS_AUTH_BYPASS=1."
            ),
        )
    if api_key is None:
        raise HTTPException(status_code=401, detail="missing X-API-Key header")
    if keys.get(_hash_key(api_key.strip())) is None:
        raise HTTPException(status_code=403, detail="invalid API key")
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Titanos console
# ═══════════════════════════════════════════════════════════════════════════
_tcfg = TitanosConfig(
    dim=10000, m=100, n=100, r=8, n_loops=12, seed=1337,
    use_recovery_gate=(os.getenv("RESILEOS_USE_RECOVERY_GATE", "0") == "1"),
)
titanos_singleton = Titanos(_tcfg)

if STATE_FILE.exists():
    try:
        titanos_singleton = Titanos.load(STATE_FILE)
        log.info("Loaded Titanos state from %s", STATE_FILE)
    except Exception as e:
        log.warning("Titanos state unreadable, starting fresh: %s", e)


def _maybe_seed_from_bundled_facts() -> int:
    try:
        stats = titanos_singleton.stats()
    except Exception as e:
        log.warning("Could not read Titanos stats; skipping seed: %s", e)
        return 0
    if int(stats.get("facts", 0)) > 0:
        return 0
    if not SEED_FILE.exists():
        log.info("Store is empty and no seed file at %s; console starts empty.", SEED_FILE)
        return 0
    try:
        raw = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("Seed file unreadable: %s", e)
        return 0

    batch: list[tuple] = []
    for row in raw.get("facts", []):
        if not isinstance(row, (list, tuple)):
            continue
        if len(row) == 3:
            s, r, o = (str(x).strip() for x in row)
            if s and r and o: batch.append((s, r, o))
        elif len(row) >= 5:
            s, r, o = (str(x).strip() for x in row[:3])
            vf = row[3] if row[3] is not None else None
            vt = row[4] if row[4] is not None else None
            if s and r and o: batch.append((s, r, o, vf, vt))

    if not batch:
        return 0

    loaded = 0
    try:
        loaded = int(titanos_singleton.learn_many(batch))
    except Exception as e:
        log.warning("learn_many failed, falling back to per-fact learn: %s", e)
        loaded = 0
        for item in batch:
            try:
                if len(item) == 3:
                    titanos_singleton.learn(item[0], item[1], item[2])
                else:
                    titanos_singleton.learn(item[0], item[1], item[2], valid_from=item[3], valid_to=item[4])
                loaded += 1
            except Exception as e2:
                log.warning("Failed to learn %r: %s", item, e2)

    if loaded:
        try:
            titanos_singleton.save(STATE_FILE)
            log.info("Seeded %d facts from %s; state saved to %s", loaded, SEED_FILE, STATE_FILE)
        except Exception as e:
            log.warning("Seeded %d facts but could not persist: %s", loaded, e)
    return loaded


_seed_count = _maybe_seed_from_bundled_facts()

try:
    _zeus_handler = make_zeus_handler()
    titanos_singleton.agency.add_child("zeus", _zeus_handler, weight=1.0)
    log.info("Zeus registered in Titanos agency group (weight=1.0)")
except Exception as e:
    log.warning("Zeus registration failed; /query will use parent only: %s", e)

try:
    wire_kin(app, titanos_singleton, auth_dep=verify_api_key)
    log.info("Kin cycle routes wired: /api/v1/kin/*, /api/v1/eat/*")
except Exception as e:
    log.warning("Kin wiring failed; kin routes unavailable: %s", e)

def _register_runtime_legions() -> None:
    """Hermes web_search is the host's default legion. Examples stay off."""
    import asyncio

    from resileos.harness.legions.search import web_search
    from resileos.kin.aphrodite import register_aphrodite_legions
    from resileos.kin.legions import LegionError, register_legion

    def web_search_legion(seen, **kwargs):
        del seen
        query = str(kwargs.get("query") or kwargs.get("q") or "")
        max_results = int(kwargs.get("max_results") or 3)
        return asyncio.run(web_search(query, max_results=max_results))

    try:
        register_legion(
            "hermes",
            web_search_legion,
            name="web_search",
            constraints={
                "action": "search",
                "writes_residual": False,
                "executes": True,
            },
        )
    except LegionError as exc:
        log.warning("web_search legion not registered: %s", exc)
    try:
        register_aphrodite_legions()
    except LegionError as exc:
        log.warning("aphrodite legions not registered: %s", exc)

try:
    _register_runtime_legions()
except Exception as e:
    log.warning("Runtime legion registration failed: %s", e)

_answer_backend_singleton: AnswerBackend | None = None

def _answer_backend() -> AnswerBackend:
    global _answer_backend_singleton
    if _answer_backend_singleton is None:
        _answer_backend_singleton = select_backend()
        log.info("Answer backend: %s", _answer_backend_singleton.name)
    return _answer_backend_singleton


def harness_tool_schemas() -> list[dict]:
    out: list[dict] = []
    for name, fn in HARNESS_TOOLS.items():
        doc = (fn.__doc__ or name).strip().split("\n")[0]
        out.append({
            "name": name,
            "description": doc,
            "parameters": {"type": "object", "properties": {}},
        })
    return out


# ── SPARQL adapter (temporal-aware) ────────────────────────────────────
class _SPARQLAdapter:
    def __init__(self, titanos) -> None:
        self._t = titanos
    def ask(self, anchor: str, relation: str, inverse: bool = False, as_of: Optional[str] = None) -> list[str]:
        return self._t.ask_list(anchor, relation, inverse=inverse, as_of=as_of)
    def iter_entities(self) -> list[str]:
        return self._t.iter_entities()


# ── Pydantic Models ────────────────────────────────────────────────────
class LearnRequest(BaseModel):
    subject: str
    relation: str
    obj: str
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None

class QueryRequest(BaseModel):
    subject: str
    relation: str
    inverse: bool = False
    render: bool = False
    as_of: Optional[str] = None
    member: str | None = None
    used_free: int = 0

class SparqlRequest(BaseModel):
    query: str

class ChainRequest(BaseModel):
    start: str
    relations: list[str]

class BatchLearnRequest(BaseModel):
    facts: list[list[Optional[str]]]

class AnswerRequest(BaseModel):
    question: Optional[str] = None
    subject: Optional[str] = None
    relation: Optional[str] = None
    inverse: bool = False
    as_of: Optional[str] = None

class ChatRequest(BaseModel):
    message: str | None = None
    text: str | None = None
    history: list = []
    hub_id: str = "anon"
    force_class: str | None = None
    last_tool_empty: bool = False
    persona: str = "honest"

    def content(self) -> str:
        return (self.message or self.text or "").strip()


def _resolve_answer_input(payload: AnswerRequest) -> tuple[Optional[str], Optional[str], bool, str]:
    subject = (payload.subject or "").strip()
    relation = (payload.relation or "").strip()
    question = (payload.question or "").strip()
    if subject and relation:
        return subject, relation, bool(payload.inverse), question or f"{subject} {relation}"
    if question:
        try:
            from titanos import parse_query as _parse_free_text
        except Exception:
            _parse_free_text = None
        if _parse_free_text is not None:
            try:
                parsed = _parse_free_text(question)
            except Exception:
                parsed = None
            if parsed is not None:
                s, r, inv = parsed
                return str(s), str(r), bool(inv), question
        try:
            ents = list(titanos_singleton.entities.keys())
            rels = list(titanos_singleton.relations.keys())
            parsed = encode_question(question, entities=ents, relations=rels)
            if parsed is not None:
                s, r, inv = parsed
                return str(s), str(r), bool(inv), question
        except Exception:
            pass
    return None, None, bool(payload.inverse), question


# ═══════════════════════════════════════════════════════════════════════════
# Routes
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/v1/stats", dependencies=[Depends(verify_api_key)])
def titanos_stats():
    base = dict(titanos_singleton.stats())
    rels = list(titanos_singleton.relations.keys())
    n = len(rels)
    import math
    base["gate"] = {
        "n_relations": n,
        "gate_capacity_bits": (math.log2(n) if n > 0 else 0.0),
        "relation_alphabet": rels,
        "frames": frame_index(),
    }
    return base

@app.get("/api/v1/tools", dependencies=[Depends(verify_api_key)])
def list_tools(q: Optional[str] = Query(default=None)):
    payload = {
        "tools": list_tool_schemas(),
        "openai": openai_tools(),
        "frames": frame_index(),
        "harness": harness_tool_schemas(),
    }
    if q is not None:
        payload["search"] = search_tool_surface(q)
    return payload

@app.post("/api/v1/tools/video_generate", dependencies=[Depends(verify_api_key)])
def video_generate(payload: dict | None = None):
    """Honest stub: no video generator is wired on this host."""
    del payload
    return {
        "status": "UNAVAILABLE",
        "detail": "No video generator is configured on this host.",
        "draft": False,
    }


@app.post("/api/v1/tools/{name}", dependencies=[Depends(verify_api_key)])
async def run_named_tool(name: str, payload: dict | None = None):
    """Run an Oracle tool, a harness tool, or the web_search legion."""
    from resileos.answer.agent_loop import _call_named_tool, _maybe_search
    from resileos.answer.tool_execute import execute_tool

    args = dict(payload or {})
    if name == "web_search":
        query = str(args.get("query") or args.get("q") or "")
        body = await _maybe_search(query)
        return {"name": name, "result": body.get("search") or {"query": query, "results": []}}
    if name == "resileos_sparql":
        return {"name": name, "result": titanos_sparql(SparqlRequest(query=str(args.get("query") or "")))}
    if name == "resileos_answer":
        return {
            "name": name,
            "result": titanos_answer(
                AnswerRequest(
                    question=args.get("question"),
                    subject=args.get("subject"),
                    relation=args.get("relation"),
                    inverse=bool(args.get("inverse") or False),
                    as_of=args.get("as_of"),
                )
            ),
        }
    if name in {"resileos_ask", "resileos_chain", "resileos_abstain"}:
        return {"name": name, "result": execute_tool(name, args, titanos=titanos_singleton)}
    try:
        result = _call_named_tool(name, args)
    except KeyError:
        raise HTTPException(404, f"unknown tool: {name}")
    except Exception as e:
        raise HTTPException(400, str(e)) from e
    return {"name": name, "result": result}


@app.get("/api/v1/ready")
def titanos_ready():
    try:
        s = titanos_singleton.stats()
    except Exception as e:
        raise HTTPException(503, f"titanos store not ready: {e}")
    return {
        "ready": True,
        "facts": int(s.get("facts", 0)),
        "facts_with_validity": int(s.get("facts_with_validity", 0)),
        "facts_expired": int(s.get("facts_expired", 0)),
        "seeded_from": str(SEED_FILE) if _seed_count else None,
        "answer_backend": _answer_backend().name,
        "auth_required": (not _AUTH_BYPASS) and _configured_key_count() > 0,
    }

@app.get("/api/v1/answer/backends", dependencies=[Depends(verify_api_key)])
def titanos_answer_backends():
    return {
        "configured": os.getenv("RESILEOS_ANSWER_BACKEND", "auto"),
        "active": _answer_backend().name,
        "backends": list_backends(),
    }

@app.post("/api/v1/chat", dependencies=[Depends(verify_api_key)])
async def titanos_chat(payload: ChatRequest):
    """Studio chat. Accepts `message` (page) or `text` (persona surface)."""
    text = payload.content()
    if not text:
        raise HTTPException(400, "text is required")
    from resileos.answer.user_profile import PERSONA_PACKS

    persona = payload.persona if payload.persona in PERSONA_PACKS else "honest"
    try:
        result = await run_agent_chat(
            titanos_singleton,
            text,
            payload.history,
            hub_id=payload.hub_id,
            force_class=payload.force_class,
            last_tool_empty=payload.last_tool_empty,
            persona=persona,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(500, str(e)) from e
    if (result.get("action_taken") or {}).get("wrote"):
        try:
            titanos_singleton.save(STATE_FILE)
        except Exception as exc:
            log.warning("chat learned but state save failed: %s", exc)
    return result

@app.post("/api/v1/upload", dependencies=[Depends(verify_api_key)])
async def upload_file(
    file: UploadFile = File(...),
    message: str = Form(""),
):
    """Handles file uploads and passes them to the agent loop for perception."""
    content = await file.read()
    file_type = file.content_type or "application/octet-stream"
    
    file_data = {
        "type": file_type,
        "size": len(content),
        "name": file.filename,
        "subject": f"file:{file.filename}"
    }

    if file_type.startswith("image/"):
        try:
            img = Image.open(io.BytesIO(content))
            file_data.update({
                "width": img.width, "height": img.height, "format": img.format
            })
        except Exception:
            pass

    result = await run_agent_chat(
        titanos_singleton, message, history=[], file_data=file_data
    )
    if (result.get("action_taken") or {}).get("wrote"):
        try:
            titanos_singleton.save(STATE_FILE)
        except Exception as exc:
            log.warning("upload learned but state save failed: %s", exc)
    return result

@app.post("/api/v1/answer", dependencies=[Depends(verify_api_key)])
def titanos_answer(payload: AnswerRequest):
    subject, relation, inverse, question = _resolve_answer_input(payload)
    if not subject or not relation:
        return {
            "question": question or (payload.question or ""), "subject": subject or "", "relation": relation or "",
            "inverse": inverse, "rows": [], "answer_text": "", "backend": _answer_backend().name,
            "status": "NONE_CHANNEL", "confidence": 0.0, "recovery_loss": 0.0,
            "reason": "gate unresolved: no subject/relation", "symbol_index": -1, "sector": "",
            "gate_capacity_bits": 0.0, "as_of": payload.as_of, "frame": derive_frame(status="NONE_CHANNEL"),
        }

    rows = titanos_singleton.ask_list(subject, relation, inverse=inverse, as_of=payload.as_of)
    confidence = 1.0 if rows else 0.0
    recovery_loss = 0.0
    if getattr(titanos_singleton.cfg, "use_recovery_gate", False):
        try:
            action, loss, reason = titanos_singleton._evaluate_recovery_gate()
        except Exception as e:
            log.warning("recovery gate failed in /answer: %s", e)
            action, loss, reason = ("CONTINUE", 0.0, "")
        recovery_loss = float(loss)
        if action == "ABSTAIN":
            return {
                "question": question or f"{subject} {relation}", "subject": subject, "relation": relation,
                "inverse": inverse, "rows": [], "answer_text": "", "backend": _answer_backend().name,
                "status": "ABSTAINED", "confidence": 0.0, "recovery_loss": recovery_loss,
                "reason": f"recovery gate: {reason}", "symbol_index": -1, "sector": "",
                "gate_capacity_bits": 0.0, "as_of": payload.as_of, "frame": derive_frame(status="ABSTAINED"),
            }

    g = None
    try:
        g = encode_gate(question or f"{subject} {relation}", entities=list(titanos_singleton.entities.keys()), relations=list(titanos_singleton.relations.keys()))
    except Exception:
        g = None

    sector = ""
    sym = -1
    cap = 0.0
    if g is not None:
        if g.subject == subject and g.relation == relation: sector = g.sector
        if g.relation == relation: sym = int(g.symbol_index)
        cap = float(g.gate_capacity_bits)

    ctx = AnswerContext(
        question=question or f"{subject} {relation}", subject=subject, relation=relation, inverse=inverse,
        rows=tuple(rows), confidence=confidence, recovery_loss=recovery_loss, sector=sector,
    )

    backend = _answer_backend()
    try:
        text = backend.render(ctx)
    except Exception as e:
        log.warning("answer backend %s failed: %s; falling back to structured", backend.name, e)
        backend = StructuredBackend()
        text = backend.render(ctx)

    status = "ANSWERED" if rows else "NO_ROWS"
    return {
        "question": ctx.question, "subject": subject, "relation": relation, "inverse": inverse,
        "rows": list(rows), "answer_text": text, "backend": backend.name, "status": status,
        "confidence": confidence, "recovery_loss": recovery_loss, "reason": "", "symbol_index": sym,
        "sector": sector, "gate_capacity_bits": cap, "as_of": payload.as_of,
        "frame": derive_frame(sector=sector, status=status, n_rows=len(rows)),
    }

@app.post("/api/v1/learn", dependencies=[Depends(verify_api_key)])
def titanos_learn(payload: LearnRequest):
    s = payload.subject.strip()
    r = payload.relation.strip()
    o = payload.obj.strip()
    if not (s and r and o):
        raise HTTPException(400, "subject/relation/obj must be non-empty")
    try:
        titanos_singleton.learn(s, r, o, valid_from=payload.valid_from, valid_to=payload.valid_to)
        titanos_singleton.save(STATE_FILE)
        return {
            "status": "SUCCESS", "records": titanos_singleton.stats()["facts"],
            "valid_from": payload.valid_from, "valid_to": payload.valid_to,
        }
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/v1/learn_batch", dependencies=[Depends(verify_api_key)])
def titanos_learn_batch(payload: BatchLearnRequest):
    if not payload.facts:
        raise HTTPException(400, "facts list is empty")
    batch: list[tuple] = []
    skipped = 0
    for row in payload.facts:
        if len(row) == 3:
            s, r, o = (str(x).strip() for x in row)
            if s and r and o: batch.append((s, r, o))
            else: skipped += 1
        elif len(row) >= 5:
            s, r, o = (str(x).strip() for x in row[:3])
            vf = row[3] if row[3] not in (None, "") else None
            vt = row[4] if row[4] not in (None, "") else None
            if s and r and o: batch.append((s, r, o, vf, vt))
            else: skipped += 1
        else: skipped += 1

    added = 0
    if batch:
        try:
            added = int(titanos_singleton.learn_many(batch))
        except Exception:
            added = 0
            for item in batch:
                try:
                    if len(item) == 3: titanos_singleton.learn(item[0], item[1], item[2])
                    else: titanos_singleton.learn(item[0], item[1], item[2], valid_from=item[3], valid_to=item[4])
                    added += 1
                except Exception: continue
    if added:
        titanos_singleton.save(STATE_FILE)
    return {"status": "SUCCESS", "added": added, "skipped": skipped, "records": titanos_singleton.stats()["facts"]}

@app.post("/api/v1/query", dependencies=[Depends(verify_api_key)])
def titanos_query(payload: QueryRequest):
    try:
        from resileos.ui.use_gate import allow_use
        member = payload.member or "anon"
        decision = allow_use(member, units=1, used_free=payload.used_free, what="query")
        if not decision.get("ok"):
            raise HTTPException(status_code=402, detail="credit required")

        sector = ""
        g = None
        try:
            g = encode_gate(f"{payload.subject} {payload.relation}", entities=list(titanos_singleton.entities.keys()), relations=list(titanos_singleton.relations.keys()))
            if g is not None and g.relation == payload.relation: sector = g.sector
        except Exception:
            sector = ""
            g = None

        titanos_singleton._route_sector = sector
        ans = None
        agency = titanos_singleton.agency

        if gbx_bypass_recurrent(sector) and not payload.inverse:
            rows = titanos_singleton.ask_list(payload.subject, payload.relation, inverse=False, as_of=payload.as_of)
            if len(rows) == 1:
                ans = Answer(value=rows[0], confidence=1.0, status="ACCEPTED", mode="FAST", loops=0, path=[(payload.subject, payload.relation, rows[0])], gate_state="LOCKED", reason="gbx sector: exact retrieval, no recurrent pass")

        if ans is None and agency.children:
            ans = run_zeus_query(agency, titanos_singleton, payload.subject, payload.relation, inverse=payload.inverse, as_of=payload.as_of)
        if ans is None:
            ans = titanos_singleton.ask_inverse(payload.subject, payload.relation, as_of=payload.as_of) if payload.inverse else titanos_singleton.ask(payload.subject, payload.relation, as_of=payload.as_of)

        out = {
            "value": ans.value, "confidence": float(ans.confidence), "status": ans.status, "mode": ans.mode, "loops": ans.loops,
            "reason": ans.reason, "gate_state": ans.gate_state, "child_name": ans.child_name, "recovery_loss": float(getattr(ans, "recovery_loss", 0.0)),
            "as_of": payload.as_of,
            "trace": [{"loop": h["loop"], "scar": float(h["scar_energy"]), "delta": float(h["delta"]), "mu": h["mu"], "deltas": float(h.get("DeltaS", 0.0)), "vol_ok": h["volume_ok"], "gate_state": h["gate_state"]} for h in ans.loop_history],
        }
        out["sector"] = sector
        out["frame"] = derive_frame(sector=sector, gate_state=str(getattr(ans, "gate_state", "") or ""), status=str(getattr(ans, "status", "") or ""), n_rows=1 if ans.value else 0)
        
        _ = prefer_child(sector=sector, gate_state=str(getattr(ans, "gate_state", "") or ""), confidence=float(ans.confidence), gate_capacity_bits=float(getattr(g, "gate_capacity_bits", 0.0) if g is not None else 0.0))
        
        if payload.render:
            ctx = context_from_answer(ans, subject=payload.subject, relation=payload.relation, inverse=payload.inverse)
            if sector:
                ctx = AnswerContext(question=ctx.question, subject=ctx.subject, relation=ctx.relation, inverse=ctx.inverse, rows=ctx.rows, confidence=ctx.confidence, recovery_loss=ctx.recovery_loss, path=ctx.path, loop_history=ctx.loop_history, gate_state=ctx.gate_state, sector=sector)
            backend = _answer_backend()
            try: text = backend.render(ctx)
            except Exception as e:
                log.warning("answer backend %s failed on /query render: %s; falling back to structured", backend.name, e)
                backend = StructuredBackend()
                text = backend.render(ctx)
            out["answer_text"] = text
            out["backend"] = backend.name
        return with_scale(out, payload.subject, payload.relation)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/v1/sparql", dependencies=[Depends(verify_api_key)])
def titanos_sparql(payload: SparqlRequest):
    q = payload.query.strip()
    if not q:
        raise HTTPException(400, "query is required")
    engine = TitanosQueryEngine(_SPARQLAdapter(titanos_singleton))
    try:
        rows = engine.execute(q)
    except QuerySyntaxError as e:
        raise HTTPException(400, f"syntax error: {e}")
    except QueryBindingError as e:
        raise HTTPException(400, f"binding error: {e}")
    except Exception as e:
        raise HTTPException(500, f"query execution failed: {e}")
    return {"rows": [list(r) for r in rows], "count": len(rows)}

@app.post("/api/v1/chain", dependencies=[Depends(verify_api_key)])
def titanos_chain(payload: ChainRequest):
    if not payload.relations:
        raise HTTPException(400, "relations must be non-empty")
    try:
        ans = titanos_singleton.chain(payload.start, payload.relations)
        return {"value": ans.value, "confidence": float(ans.confidence), "status": ans.status, "mode": ans.mode, "path": ans.path, "reason": ans.reason}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/v1/save", dependencies=[Depends(verify_api_key)])
def titanos_save():
    titanos_singleton.save(STATE_FILE)
    return {"status": "SAVED", "path": str(STATE_FILE)}


# ═══════════════════════════════════════════════════════════════════════════
# Hades checkpoints and optional tools
# ═══════════════════════════════════════════════════════════════════════════

def _hades_store():
    from resileos.kin.hades import make_hades
    from resileos.kin.wiring import get_kin_bundle

    bundle = get_kin_bundle()
    store = getattr(bundle, "_hades", None)
    if store is None:
        store = make_hades()
        bundle._hades = store
    return bundle, store


@app.get("/api/v1/kin/hades/list", dependencies=[Depends(verify_api_key)])
def hades_list():
    _, store = _hades_store()
    checkpoints = []
    for cid in store.list_ids():
        ckpt = store.load(cid)
        if ckpt is None:
            checkpoints.append({"id": cid, "name": cid})
            continue
        checkpoints.append({
            "id": ckpt.id,
            "name": ckpt.lesson or ckpt.id,
            "created_at": ckpt.created_at,
            "verified": ckpt.verified,
        })
    return {"checkpoints": checkpoints}


@app.post("/api/v1/kin/hades/restore", dependencies=[Depends(verify_api_key)])
def hades_restore(payload: dict):
    checkpoint_id = str((payload or {}).get("checkpoint_id") or (payload or {}).get("id") or "").strip()
    if not checkpoint_id:
        raise HTTPException(400, "checkpoint_id is required")
    bundle, store = _hades_store()
    ckpt = store.load(checkpoint_id)
    if ckpt is None:
        raise HTTPException(404, f"unknown checkpoint: {checkpoint_id}")
    packet = store.restore_fresh(checkpoint_id)
    bundle.control = packet
    return {
        "status": "RESTORED",
        "checkpoint_id": checkpoint_id,
        "lesson": ckpt.lesson,
        "residual_hash": ckpt.residual_packet_hash,
        "verified_previous": ckpt.verified,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Substrate (unchanged)
# ═══════════════════════════════════════════════════════════════════════════
HIDDEN_DIM = int(os.getenv("RESILEOS_HIDDEN_DIM", "128"))
KERNEL_DIM = int(os.getenv("RESILEOS_KERNEL_DIM", "1"))
MIN_TRAIN_STEPS = int(os.getenv("RESILEOS_MIN_TRAIN_STEPS", "5"))

class SubstrateContainer:
    def __init__(self) -> None:
        torch.manual_seed(42)
        kernel = torch.zeros(HIDDEN_DIM, KERNEL_DIM)
        kernel[0, 0] = 1.0
        self.hidden_dim = HIDDEN_DIM
        self.kernel_dim = KERNEL_DIM
        self.geo_head = LowRankMetricHead(hidden_dim=HIDDEN_DIM)
        self.fep_head = VerifiableFEPReductionHead(hidden_dim=HIDDEN_DIM, L_H_kernel=kernel, rank=1)
        trainable = (list(self.geo_head.parameters()) + list(self.fep_head.parameters()))
        self.optimizer = torch.optim.AdamW(trainable, lr=1e-3)
        self.is_trained = False
        self.training_steps = 0
        self.last_train_metrics: dict | None = None

    def train_step(self, seq_len: int, g_field: float, epsilon: float, seed: int) -> dict:
        self.optimizer.zero_grad()
        trunk = simulate_axiom_d(dim=self.hidden_dim, seq_len=seq_len, epsilon=epsilon, g_field=g_field, seed=seed)
        X = torch.zeros_like(trunk)
        X[:, :-1] = trunk[:, 1:] - trunk[:, :-1]
        X[:, -1] = X[:, -2]
        G = torch.ones(1, seq_len, 1)
        _, geo_loss = self.geo_head(trunk, X)
        _, fep_loss = self.fep_head(trunk, G)
        total = geo_loss + fep_loss
        total.backward()
        self.optimizer.step()
        self.training_steps += 1
        metrics = {"geo": float(geo_loss.item()), "fep": float(fep_loss.item()), "total": float(total.item())}
        self.last_train_metrics = metrics
        return metrics

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        torch.save({
            "geo_head": self.geo_head.state_dict(), "fep_head": self.fep_head.state_dict(), "optimizer": self.optimizer.state_dict(),
            "is_trained": self.is_trained, "training_steps": self.training_steps, "last_train_metrics": self.last_train_metrics,
            "hidden_dim": self.hidden_dim, "kernel_dim": self.kernel_dim,
        }, tmp)
        tmp.replace(path)

    def load(self, path: Path) -> bool:
        if not path.exists(): return False
        try:
            ckpt = torch.load(path, map_location="cpu", weights_only=False)
            ckpt_hidden = int(ckpt.get("hidden_dim", self.hidden_dim))
            if ckpt_hidden != self.hidden_dim:
                log.warning("Substrate checkpoint hidden_dim=%d != current %d; ignoring checkpoint and starting fresh", ckpt_hidden, self.hidden_dim)
                return False
            self.geo_head.load_state_dict(ckpt["geo_head"])
            self.fep_head.load_state_dict(ckpt["fep_head"])
            self.optimizer.load_state_dict(ckpt["optimizer"])
            self.is_trained = bool(ckpt.get("is_trained", False))
            self.training_steps = int(ckpt.get("training_steps", 0))
            self.last_train_metrics = ckpt.get("last_train_metrics")
            log.info("Substrate restored: trained=%s steps=%d", self.is_trained, self.training_steps)
            return True
        except Exception as e:
            log.warning("Substrate state unreadable, starting fresh: %s", e)
            return False

substrate_singleton = SubstrateContainer()
substrate_singleton.load(SUBSTRATE_STATE_PATH)

class VerificationRequest(BaseModel):
    hierarchical_states: list = Field(..., description="[1, T, L, D] hierarchy of hidden states")
    velocity_direction: list = Field(..., description="[1, T, D] velocity")
    g_field_sequence: list = Field(..., description="[1, T, 1] coherence")

class TrainRequest(BaseModel):
    steps: int = 10
    seq_len: int = 64
    g_field: float = 0.85
    base_epsilon: float = 0.1
    seed: int = 0

class SweepRequest(BaseModel):
    mode: str = "simulate"
    epsilons: list[float] = [0.1, 0.05, 0.02, 0.01, 0.005, 0.001]
    metric: str = "rmse"
    g_field: float = 0.85
    seq_len: int = 64
    trajectory: list | None = None

@app.get("/api/v1/substrate_stats")
def substrate_stats():
    return {
        "hidden_dim": substrate_singleton.hidden_dim, "kernel_dim": substrate_singleton.kernel_dim,
        "is_trained": substrate_singleton.is_trained, "training_steps": substrate_singleton.training_steps,
        "min_train_steps": MIN_TRAIN_STEPS, "last_train_metrics": substrate_singleton.last_train_metrics,
        "bridge_locked": True, "state_path": str(SUBSTRATE_STATE_PATH),
    }

@app.post("/api/v1/train_substrate", dependencies=[Depends(verify_api_key)])
def train_substrate(payload: TrainRequest):
    if payload.steps < 1 or payload.steps > 500: raise HTTPException(400, "steps must be in [1, 500]")
    history = []
    for i in range(payload.steps):
        eps = payload.base_epsilon / (1.0 + 0.3 * i)
        try:
            metrics = substrate_singleton.train_step(seq_len=payload.seq_len, g_field=payload.g_field, epsilon=eps, seed=payload.seed + i)
        except Exception as e:
            raise HTTPException(500, f"training step {i} failed: {e}")
        history.append({"step": i, "epsilon": eps, **metrics})
    if substrate_singleton.training_steps >= MIN_TRAIN_STEPS: substrate_singleton.is_trained = True
    with _substrate_lock:
        try: substrate_singleton.save(SUBSTRATE_STATE_PATH)
        except Exception as e: log.warning("Substrate save failed: %s", e)
    return {"status": ("trained" if substrate_singleton.is_trained else "partial"), "total_steps": substrate_singleton.training_steps, "is_trained": substrate_singleton.is_trained, "history": history}

@app.post("/api/v1/verify_manifold", dependencies=[Depends(verify_api_key)])
def verify_manifold(payload: VerificationRequest):
    if not substrate_singleton.is_trained:
        raise HTTPException(400, f"Substrate is UNTRAINED. completed_steps={substrate_singleton.training_steps}, min={MIN_TRAIN_STEPS}. Call POST /api/v1/train_substrate first.")
    try:
        h = torch.tensor(payload.hierarchical_states, dtype=torch.float32)
        x = torch.tensor(payload.velocity_direction, dtype=torch.float32)
        g = torch.tensor(payload.g_field_sequence, dtype=torch.float32)
        if h.dim() != 4 or h.size(0) != 1: raise ValueError(f"hierarchical_states must be [1, T, L, D], got {tuple(h.shape)}")
        if h.size(-1) != substrate_singleton.hidden_dim: raise ValueError(f"last dim must equal hidden_dim ({substrate_singleton.hidden_dim}), got {h.size(-1)}")
        trunk = h.mean(dim=2)
        with torch.no_grad():
            _, geo_loss = substrate_singleton.geo_head(trunk, x)
            psi_s, fep_loss = substrate_singleton.fep_head(trunk, g)
        return {"status": "verified", "parallel_transport_penalty": float(geo_loss.item()), "fep_ode_alignment_loss": float(fep_loss.item()), "slow_subspace_trajectory": (psi_s.squeeze(0).squeeze(-1).tolist())}
    except HTTPException: raise
    except Exception as e: raise HTTPException(500, f"manifold error: {e}")

@app.post("/api/v1/sweep_epsilon", dependencies=[Depends(verify_api_key)])
def sweep_epsilon(payload: SweepRequest):
    if payload.metric not in ("rmse", "mse"): raise HTTPException(400, f"metric must be 'rmse' | 'mse', got {payload.metric!r}")
    if len(payload.epsilons) < 2: raise HTTPException(400, "at least two epsilon values required")
    if any(e <= 0.0 for e in payload.epsilons): raise HTTPException(400, "epsilons must all be > 0")
    dim = substrate_singleton.hidden_dim
    if payload.mode == "simulate":
        def factory(eps: float) -> torch.Tensor:
            return simulate_axiom_d(dim=dim, seq_len=payload.seq_len, epsilon=eps, g_field=payload.g_field, seed=0)
    elif payload.mode == "data":
        if payload.trajectory is None: raise HTTPException(400, "mode='data' requires a trajectory array")
        arr = np.asarray(payload.trajectory, dtype=np.float32)
        if arr.ndim == 2: arr = arr[None, ...]
        if arr.ndim != 3: raise HTTPException(400, f"trajectory must be [T, D] or [K, T, D], got {arr.shape}")
        if arr.shape[-1] != dim: raise HTTPException(400, f"trajectory last dim {arr.shape[-1]} != hidden_dim {dim}")
        trunk_ref = torch.tensor(arr.mean(axis=0)[None, ...], dtype=torch.float32)
        def factory(eps: float) -> torch.Tensor:
            t = trunk_ref.clone(); t[:, 0, 0] = 1.5 + eps; return t
    else: raise HTTPException(400, f"mode must be 'simulate' | 'data', got {payload.mode!r}")
    try:
        sample = factory(payload.epsilons[0])
        G = torch.ones(1, sample.shape[1], 1)
        result = substrate_singleton.fep_head.sweep_epsilon(factory, payload.epsilons, G, metric=payload.metric)
    except Exception as e: raise HTTPException(500, f"sweep failed: {e}")
    slope = result["slope"]
    if payload.metric == "rmse":
        verdict = "consistent with linear O(ε) residual (RES-600 §4)" if 0.85 <= slope <= 1.15 else ("sub-linear; check trajectory or discretization" if slope < 0.85 else "super-linear; check discretization error dominance")
    else:
        verdict = "consistent with O(ε) residual under MSE metric" if 1.85 <= slope <= 2.15 else "unexpected MSE scaling"
    return {"source": payload.mode, "dim": dim, "g_field": payload.g_field, **result, "verdict": verdict}

# ═══════════════════════════════════════════════════════════════════════════
# leCore integration (unchanged)
# ═══════════════════════════════════════════════════════════════════════════
_lecore = LeCoreClient()

class LeCoreRouteRequest(BaseModel):
    query: str

@app.get("/api/v1/lecore/health")
def lecore_health():
    try:
        return {"available": True, **_lecore.health()}
    except (LeCoreUnreachable, LeCoreError) as e:
        return {"available": False, "error": str(e)}

@app.post("/api/v1/lecore/route", dependencies=[Depends(verify_api_key)])
def lecore_route(payload: LeCoreRouteRequest):
    query = payload.query.strip()
    if not query: raise HTTPException(400, "query is required")
    try:
        caps = _lecore.search(query)
    except (LeCoreUnreachable, LeCoreError) as e:
        return {"available": False, "error": str(e)}
    return {"available": True, "query": query, "capabilities": [{"name": c.name, "description": c.description, "score": c.score} for c in caps]}


# ═══════════════════════════════════════════════════════════════════════════
# Hub ledger, studio, and UI surfaces
# ═══════════════════════════════════════════════════════════════════════════
from resileos.chat.ledger import (  # noqa: E402
    delete_user_triple,
    edit_user_triple,
    list_user_ledger,
)
from resileos.chat.conversations import register_conversation_routes  # noqa: E402
from resileos.studio.routes import register_studio_routes  # noqa: E402
from resileos.ui.routes import register_ui_routes  # noqa: E402


class LedgerEditRequest(BaseModel):
    relation: str
    obj: str
    new_relation: str | None = None
    new_obj: str | None = None


def _save_titanos() -> None:
    titanos_singleton.save(STATE_FILE)


@app.get(
    "/api/v1/hub/{hub_id}/ledger",
    dependencies=[Depends(verify_api_key)],
)
def hub_ledger_list(hub_id: str):
    try:
        return list_user_ledger(titanos_singleton, hub_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.put(
    "/api/v1/hub/{hub_id}/ledger",
    dependencies=[Depends(verify_api_key)],
)
def hub_ledger_edit(hub_id: str, payload: LedgerEditRequest):
    try:
        ledger = edit_user_triple(
            titanos_singleton,
            hub_id,
            payload.relation,
            payload.obj,
            new_relation=payload.new_relation,
            new_obj=payload.new_obj,
        )
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if ledger.get("wrote"):
        try:
            _save_titanos()
        except Exception as exc:
            log.warning("ledger edit saved in memory but not on disk: %s", exc)
    return ledger


@app.delete(
    "/api/v1/hub/{hub_id}/ledger",
    dependencies=[Depends(verify_api_key)],
)
def hub_ledger_delete(
    hub_id: str,
    relation: str = Query(...),
    obj: str = Query(...),
):
    try:
        ledger = delete_user_triple(titanos_singleton, hub_id, relation, obj)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    try:
        _save_titanos()
    except Exception as exc:
        log.warning("ledger delete saved in memory but not on disk: %s", exc)
    return ledger


async def conversation_key_id(
    api_key: str | None = Depends(_api_key_header),
) -> str:
    """Auth for conversation routes. Returns the key hash, never the key."""
    await verify_api_key(api_key)
    if api_key and api_key.strip():
        return _hash_key(api_key.strip())
    if _AUTH_BYPASS:
        return "auth-bypass"
    raise HTTPException(status_code=401, detail="missing X-API-Key header")


def _mount_surfaces() -> None:
    register_studio_routes(app, verify_api_key)
    register_ui_routes(
        app,
        verify_api_key,
        get_titanos=lambda: titanos_singleton,
        save=_save_titanos,
    )
    register_conversation_routes(app, conversation_key_id)


_mount_surfaces()
