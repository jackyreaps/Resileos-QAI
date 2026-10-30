"""
FastAPI backend for Resileos-QAI.

Two endpoint groups on one app:

Titanos console (application layer):
    GET  /api/v1/stats
    GET  /api/v1/ready
    GET  /api/v1/tools
    POST /api/v1/learn
    POST /api/v1/learn_batch
    POST /api/v1/query               (routed through Zeus with fallthrough)
    POST /api/v1/sparql              (query language, RES-322)
    POST /api/v1/chain
    POST /api/v1/answer              (retrieve + render, RES-327)
    GET  /api/v1/answer/backends     (backend availability report)
    POST /api/v1/save

Substrate (QD-TER two-head system, RES-600/601/602):
    GET  /api/v1/substrate_stats
    POST /api/v1/train_substrate
    POST /api/v1/verify_manifold     (gated on is_trained)
    POST /api/v1/sweep_epsilon       (ungated diagnostic)

Integration (leCore capability router):
    POST /api/v1/lecore/route
    GET  /api/v1/lecore/health

Auth: if RESILEOS_API_KEY is set, every route except
/api/v1/ready, /api/v1/substrate_stats, and /api/v1/lecore/health
requires a matching X-API-Key header. If unset, the check bypasses
(dev default).
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import sys
import threading
from pathlib import Path

import numpy as np
import torch
from fastapi import Depends, FastAPI, HTTPException
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
    prefer_child,
    select_backend,
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
from titanos import Titanos, TitanosConfig  # noqa: E402

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("resileos.api")

app = FastAPI(title="Resileos-QAI")

STATE_FILE = ROOT / "titanos_live_state.json"
SEED_FILE = ROOT / "configs" / "titanos-facts.json"

# Substrate state persistence path. In Docker, set
# RESILEOS_SUBSTRATE_STATE=/app/data/substrate_state.pt so the volume
# mount catches it. Local dev falls back to ./data/substrate_state.pt.
SUBSTRATE_STATE_PATH = Path(
    os.getenv(
        "RESILEOS_SUBSTRATE_STATE",
        str(ROOT / "data" / "substrate_state.pt"),
    )
)

# Serializes writes to the substrate checkpoint. Training itself is not
# fully locked — concurrent training calls can interleave optimizer steps.
# The single-worker single-replica deployment invariant (see HOSTING.md)
# is what keeps training coherent in production.
_substrate_lock = threading.Lock()


# ═══════════════════════════════════════════════════════════════════════════
# API key auth (constant-time; bypassed when RESILEOS_API_KEY is unset)
# ═══════════════════════════════════════════════════════════════════════════
_API_KEY_NAME = "X-API-Key"
_api_key_header = APIKeyHeader(name=_API_KEY_NAME, auto_error=False)
_EXPECTED_API_KEY = os.getenv("RESILEOS_API_KEY", "").strip()


async def verify_api_key(
    api_key: str | None = Depends(_api_key_header),
) -> None:
    """Constant-time API key check.

    - If RESILEOS_API_KEY is empty (dev default), the check bypasses.
    - If set, the header must match exactly (timing-safe comparison).
    - Missing header + set key -> 403.

    Applied via ``dependencies=[Depends(verify_api_key)]`` on every
    non-health route. Health endpoints (/api/v1/ready,
    /api/v1/substrate_stats, /api/v1/lecore/health) stay open so that
    the Docker HEALTHCHECK and any liveness probe work without
    credentials.
    """
    if not _EXPECTED_API_KEY:
        return
    if api_key is not None and hmac.compare_digest(
        api_key, _EXPECTED_API_KEY
    ):
        return
    raise HTTPException(
        status_code=HTTP_403_FORBIDDEN,
        detail="Unauthorized: invalid or missing X-API-Key",
    )


# ═══════════════════════════════════════════════════════════════════════════
# Titanos console
# ═══════════════════════════════════════════════════════════════════════════
_tcfg = TitanosConfig(
    dim=10000,
    m=100,
    n=100,
    r=8,
    n_loops=12,
    seed=1337,
    use_recovery_gate=(
        os.getenv("RESILEOS_USE_RECOVERY_GATE", "0") == "1"
    ),
)
titanos_singleton = Titanos(_tcfg)

if STATE_FILE.exists():
    try:
        titanos_singleton = Titanos.load(STATE_FILE)
        log.info("Loaded Titanos state from %s", STATE_FILE)
    except Exception as e:
        log.warning("Titanos state unreadable, starting fresh: %s", e)


def _maybe_seed_from_bundled_facts() -> int:
    """Seed the console from configs/titanos-facts.json when the store is
    empty. Returns the number of facts loaded (0 = no seed performed).

    Uses `learn_many()` so the attractor's Hopfield matrix is rebuilt
    once at the end of the batch, not per fact. Falls back to per-fact
    `learn()` if the batch path raises.
    """
    try:
        stats = titanos_singleton.stats()
    except Exception as e:
        log.warning("Could not read Titanos stats; skipping seed: %s", e)
        return 0
    if int(stats.get("facts", 0)) > 0:
        return 0
    if not SEED_FILE.exists():
        log.info(
            "Store is empty and no seed file at %s; console starts empty.",
            SEED_FILE,
        )
        return 0
    try:
        raw = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("Seed file unreadable: %s", e)
        return 0

    batch: list[tuple[str, str, str]] = []
    for row in raw.get("facts", []):
        if not isinstance(row, (list, tuple)) or len(row) != 3:
            continue
        s, r, o = (str(x).strip() for x in row)
        if not (s and r and o):
            continue
        batch.append((s, r, o))

    if not batch:
        return 0

    loaded = 0
    try:
        loaded = int(titanos_singleton.learn_many(batch))
    except Exception as e:
        log.warning(
            "learn_many failed, falling back to per-fact learn: %s", e
        )
        loaded = 0
        for s, r, o in batch:
            try:
                titanos_singleton.learn(s, r, o)
                loaded += 1
            except Exception as e2:
                log.warning(
                    "Failed to learn %r %r %r: %s", s, r, o, e2
                )

    if loaded:
        try:
            titanos_singleton.save(STATE_FILE)
            log.info(
                "Seeded %d facts from %s; state saved to %s",
                loaded, SEED_FILE, STATE_FILE,
            )
        except Exception as e:
            log.warning(
                "Seeded %d facts but could not persist: %s", loaded, e
            )
    return loaded


_seed_count = _maybe_seed_from_bundled_facts()


# ── Zeus wiring ─────────────────────────────────────────────────────────
# Zeus is registered as an AgencyChild on the Titanos singleton's own
# AgencyGroup, so stats()["agency"] reflects the registration. The
# query route reads from the same group; if Zeus declines (returns
# None), the parent answers directly (RES-324 doctrine).
try:
    _zeus_handler = make_zeus_handler()
    titanos_singleton.agency.add_child("zeus", _zeus_handler, weight=1.0)
    log.info("Zeus registered in Titanos agency group (weight=1.0)")
except Exception as e:
    log.warning(
        "Zeus registration failed; /query will use parent only: %s", e
    )


# ── Answer backend (RES-327) ───────────────────────────────────────────
# Selected once at first use from RESILEOS_ANSWER_BACKEND (default auto:
# local_hf -> hosted -> structured). The structured backend is always
# available; the others depend on transformers / an API key.
_answer_backend_singleton: AnswerBackend | None = None


def _answer_backend() -> AnswerBackend:
    global _answer_backend_singleton
    if _answer_backend_singleton is None:
        _answer_backend_singleton = select_backend()
        log.info(
            "Answer backend: %s", _answer_backend_singleton.name
        )
    return _answer_backend_singleton


# ── SPARQL adapter ──────────────────────────────────────────────────────
class _SPARQLAdapter:
    """Bridges Titanos to the RES-322 `_Core` Protocol.

    The query engine calls `core.ask(anchor, relation, inverse=...)` and
    expects `list[str]`. Titanos exposes `ask_list` which returns
    exactly that. `iter_entities` passthrough enables full-scan queries.
    """

    def __init__(self, titanos) -> None:
        self._t = titanos

    def ask(self, anchor: str, relation: str,
            inverse: bool = False) -> list[str]:
        return self._t.ask_list(anchor, relation, inverse=inverse)

    def iter_entities(self) -> list[str]:
        return self._t.iter_entities()


class LearnRequest(BaseModel):
    subject: str
    relation: str
    obj: str


class QueryRequest(BaseModel):
    subject: str
    relation: str
    inverse: bool = False
    render: bool = False


class SparqlRequest(BaseModel):
    query: str


class ChainRequest(BaseModel):
    start: str
    relations: list[str]


class BatchLearnRequest(BaseModel):
    facts: list[list[str]]


class AnswerRequest(BaseModel):
    """Either free-text `question`, or structured `subject`+`relation`.

    If both are provided, the structured fields win and `question` is
    used only for display. If only `question` is provided, the parser
    in scripts/titanos.py is used to extract (subject, relation,
    inverse). If neither resolves, the route returns 400.
    """
    question: str | None = None
    subject: str | None = None
    relation: str | None = None
    inverse: bool = False


def _resolve_answer_input(
    payload: AnswerRequest,
) -> tuple[str | None, str | None, bool, str]:
    """Return (subject, relation, inverse, question_for_display)."""
    subject = (payload.subject or "").strip()
    relation = (payload.relation or "").strip()
    question = (payload.question or "").strip()

    if subject and relation:
        display = question or f"{subject} {relation}"
        return subject, relation, bool(payload.inverse), display

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
        # Framework-native fallback: resolve against live store vocab
        # (no HF / external LLM).
        try:
            ents = list(titanos_singleton.entities.keys())
            rels = list(titanos_singleton.relations.keys())
            parsed = encode_question(
                question, entities=ents, relations=rels
            )
            if parsed is not None:
                s, r, inv = parsed
                return str(s), str(r), bool(inv), question
        except Exception:
            pass

    return None, None, bool(payload.inverse), question


@app.get(
    "/api/v1/stats",
    dependencies=[Depends(verify_api_key)],
)
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


@app.get(
    "/api/v1/tools",
    dependencies=[Depends(verify_api_key)],
)
def list_tools():
    """Tool schemas for external frontier mouths + frame tags."""
    return {
        "tools": list_tool_schemas(),
        "openai": openai_tools(),
        "frames": frame_index(),
    }


@app.get("/api/v1/ready")
def titanos_ready():
    """Readiness probe. Returns 503 until the Titanos store is open.

    Open (no auth): the Docker HEALTHCHECK and any liveness probe
    depend on this endpoint being reachable without credentials.
    """
    try:
        s = titanos_singleton.stats()
    except Exception as e:
        raise HTTPException(503, f"titanos store not ready: {e}")
    return {
        "ready": True,
        "facts": int(s.get("facts", 0)),
        "seeded_from": str(SEED_FILE) if _seed_count else None,
        "answer_backend": _answer_backend().name,
        "auth_required": bool(_EXPECTED_API_KEY),
    }


@app.get(
    "/api/v1/answer/backends",
    dependencies=[Depends(verify_api_key)],
)
def titanos_answer_backends():
    """Availability report for the three answer backends."""
    return {
        "configured": os.getenv("RESILEOS_ANSWER_BACKEND", "auto"),
        "active": _answer_backend().name,
        "backends": list_backends(),
    }


@app.post(
    "/api/v1/answer",
    dependencies=[Depends(verify_api_key)],
)
def titanos_answer(payload: AnswerRequest):
    """Retrieve exact rows, render one sentence.

    Fast path: no recurrent loop, no sigma gate. Uses ``ask_list`` so
    multi-valued relations return every row. The F2 recovery gate, if
    enabled on the singleton, is checked once against the live phase
    field; if the field has decohered, the route abstains before
    rendering. See ``docs/320-titanos/answer.md`` (RES-327) for the
    contract.
    """
    subject, relation, inverse, question = _resolve_answer_input(payload)
    if not subject or not relation:
        # None channel: gate did not select a symbol (unresolved free-text
        # or missing structured fields). Do not invent a triple.
        return {
            "question": question or (payload.question or ""),
            "subject": subject or "",
            "relation": relation or "",
            "inverse": inverse,
            "rows": [],
            "answer_text": "",
            "backend": _answer_backend().name,
            "status": "NONE_CHANNEL",
            "confidence": 0.0,
            "recovery_loss": 0.0,
            "reason": "gate unresolved: no subject/relation",
            "symbol_index": -1,
            "sector": "",
            "gate_capacity_bits": 0.0,
        }

    rows = titanos_singleton.ask_list(
        subject, relation, inverse=inverse
    )
    confidence = 1.0 if rows else 0.0

    recovery_loss = 0.0
    if getattr(titanos_singleton.cfg, "use_recovery_gate", False):
        try:
            action, loss, reason = (
                titanos_singleton._evaluate_recovery_gate()
            )
        except Exception as e:
            log.warning("recovery gate failed in /answer: %s", e)
            action, loss, reason = ("CONTINUE", 0.0, "")
        recovery_loss = float(loss)
        if action == "ABSTAIN":
            return {
                "question": question or f"{subject} {relation}",
                "subject": subject,
                "relation": relation,
                "inverse": inverse,
                "rows": [],
                "answer_text": "",
                "backend": _answer_backend().name,
                "status": "ABSTAINED",
                "confidence": 0.0,
                "recovery_loss": recovery_loss,
                "reason": f"recovery gate: {reason}",
                "symbol_index": -1,
                "sector": "",
                "gate_capacity_bits": 0.0,
            }

    # Single gate encode: sector + symbol_index + capacity (consistent).
    g = None
    try:
        g = encode_gate(
            question or f"{subject} {relation}",
            entities=list(titanos_singleton.entities.keys()),
            relations=list(titanos_singleton.relations.keys()),
        )
    except Exception:
        g = None

    sector = ""
    sym = -1
    cap = 0.0
    if g is not None:
        if g.subject == subject and g.relation == relation:
            sector = g.sector
        if g.relation == relation:
            sym = int(g.symbol_index)
        cap = float(g.gate_capacity_bits)

    ctx = AnswerContext(
        question=question or f"{subject} {relation}",
        subject=subject,
        relation=relation,
        inverse=inverse,
        rows=tuple(rows),
        confidence=confidence,
        recovery_loss=recovery_loss,
        sector=sector,
    )

    backend = _answer_backend()
    try:
        text = backend.render(ctx)
    except Exception as e:
        log.warning(
            "answer backend %s failed: %s; falling back to structured",
            backend.name, e,
        )
        backend = StructuredBackend()
        text = backend.render(ctx)

    status = "ANSWERED" if rows else "NO_ROWS"
    return {
        "question": ctx.question,
        "subject": subject,
        "relation": relation,
        "inverse": inverse,
        "rows": list(rows),
        "answer_text": text,
        "backend": backend.name,
        "status": status,
        "confidence": confidence,
        "recovery_loss": recovery_loss,
        "reason": "",
        "symbol_index": sym,
        "sector": sector,
        "gate_capacity_bits": cap,
    }


@app.post(
    "/api/v1/learn",
    dependencies=[Depends(verify_api_key)],
)
def titanos_learn(payload: LearnRequest):
    s, r, o = (
        payload.subject.strip(),
        payload.relation.strip(),
        payload.obj.strip(),
    )
    if not (s and r and o):
        raise HTTPException(400, "subject/relation/obj must be non-empty")
    try:
        titanos_singleton.learn(s, r, o)
        titanos_singleton.save(STATE_FILE)
        return {
            "status": "SUCCESS",
            "records": titanos_singleton.stats()["facts"],
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post(
    "/api/v1/learn_batch",
    dependencies=[Depends(verify_api_key)],
)
def titanos_learn_batch(payload: BatchLearnRequest):
    if not payload.facts:
        raise HTTPException(400, "facts list is empty")
    batch: list[tuple[str, str, str]] = []
    for row in payload.facts:
        if len(row) != 3:
            continue
        s, r, o = (x.strip() for x in row)
        if not (s and r and o):
            continue
        batch.append((s, r, o))
    added = 0
    if batch:
        try:
            added = int(titanos_singleton.learn_many(batch))
        except Exception:
            added = 0
            for s, r, o in batch:
                try:
                    titanos_singleton.learn(s, r, o)
                    added += 1
                except Exception:
                    continue
    if added:
        titanos_singleton.save(STATE_FILE)
    return {
        "status": "SUCCESS",
        "added": added,
        "records": titanos_singleton.stats()["facts"],
    }


@app.post(
    "/api/v1/query",
    dependencies=[Depends(verify_api_key)],
)
def titanos_query(payload: QueryRequest):
    """Route through Zeus with parent fallthrough.

    Zeus handles structured resolution first (it delegates to the
    parent's `ask` for simple queries). If Zeus returns None — decline
    — the parent answers directly. Agency fitness is recorded
    internally by run_zeus_query.
    """
    try:
        # Sector from gate encoder (routing label only).
        sector = ""
        try:
            g = encode_gate(
                f"{payload.subject} {payload.relation}",
                entities=list(titanos_singleton.entities.keys()),
                relations=list(titanos_singleton.relations.keys()),
            )
            if g is not None and g.relation == payload.relation:
                sector = g.sector
        except Exception:
            sector = ""

        # Publish sector for Zeus cheap-decline (fitness still updates).
        titanos_singleton._route_sector = sector
        _ = prefer_child(sector=sector)

        ans = None
        agency = titanos_singleton.agency

        # gbx_like fast path: exact ask_list confidence, skip long
        # recurrent when the band already has a unique row.
        if gbx_bypass_recurrent(sector) and not payload.inverse:
            rows = titanos_singleton.ask_list(
                payload.subject, payload.relation, inverse=False
            )
            if len(rows) == 1:
                ans = titanos_singleton.ask(
                    payload.subject, payload.relation
                )

        # Always invoke Zeus when present so fitness tracks full mix.
        # Zeus declines on gbx_like via parent._route_sector.
        if ans is None and agency.children:
            ans = run_zeus_query(
                agency,
                titanos_singleton,
                payload.subject,
                payload.relation,
                inverse=payload.inverse,
            )
        if ans is None:
            ans = (
                titanos_singleton.ask_inverse(
                    payload.subject, payload.relation)
                if payload.inverse
                else titanos_singleton.ask(
                    payload.subject, payload.relation)
            )
        out = {
            "value": ans.value,
            "confidence": float(ans.confidence),
            "status": ans.status,
            "mode": ans.mode,
            "loops": ans.loops,
            "reason": ans.reason,
            "gate_state": ans.gate_state,
            "child_name": ans.child_name,
            "recovery_loss": float(getattr(ans, "recovery_loss", 0.0)),
            "trace": [
                {
                    "loop": h["loop"],
                    "scar": float(h["scar_energy"]),
                    "delta": float(h["delta"]),
                    "mu": h["mu"],
                    "deltas": float(h.get("DeltaS", 0.0)),
                    "vol_ok": h["volume_ok"],
                    "gate_state": h["gate_state"],
                }
                for h in ans.loop_history
            ],
        }
        out["sector"] = sector
        if payload.render:
            ctx = context_from_answer(
                ans,
                subject=payload.subject,
                relation=payload.relation,
                inverse=payload.inverse,
            )
            # Prefer gate sector on the mouth context when present.
            if sector:
                ctx = AnswerContext(
                    question=ctx.question,
                    subject=ctx.subject,
                    relation=ctx.relation,
                    inverse=ctx.inverse,
                    rows=ctx.rows,
                    confidence=ctx.confidence,
                    recovery_loss=ctx.recovery_loss,
                    path=ctx.path,
                    loop_history=ctx.loop_history,
                    gate_state=ctx.gate_state,
                    sector=sector,
                )
            backend = _answer_backend()
            try:
                text = backend.render(ctx)
            except Exception as e:
                log.warning(
                    "answer backend %s failed on /query render: %s; "
                    "falling back to structured",
                    backend.name, e,
                )
                backend = StructuredBackend()
                text = backend.render(ctx)
            out["answer_text"] = text
            out["backend"] = backend.name
        return out
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post(
    "/api/v1/sparql",
    dependencies=[Depends(verify_api_key)],
)
def titanos_sparql(payload: SparqlRequest):
    """Execute a query in the RES-322 grammar against the live state.

    Examples:
        SELECT ?o WHERE alice --knows--> ?o
        SELECT ?s WHERE ?s <--knows-- bob
        SELECT ?o WHERE alice --knows--> ?o AND ?o --works_at--> acme
        SELECT ?s, ?o WHERE ?s --knows--> ?o
    """
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
    return {
        "rows": [list(r) for r in rows],
        "count": len(rows),
    }


@app.post(
    "/api/v1/chain",
    dependencies=[Depends(verify_api_key)],
)
def titanos_chain(payload: ChainRequest):
    if not payload.relations:
        raise HTTPException(400, "relations must be non-empty")
    try:
        ans = titanos_singleton.chain(
            payload.start, payload.relations
        )
        return {
            "value": ans.value,
            "confidence": float(ans.confidence),
            "status": ans.status,
            "mode": ans.mode,
            "path": ans.path,
            "reason": ans.reason,
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post(
    "/api/v1/save",
    dependencies=[Depends(verify_api_key)],
)
def titanos_save():
    titanos_singleton.save(STATE_FILE)
    return {"status": "SAVED", "path": str(STATE_FILE)}


# ═══════════════════════════════════════════════════════════════════════════
# Substrate (QD-TER two-head system)
# ═══════════════════════════════════════════════════════════════════════════
HIDDEN_DIM = int(os.getenv("RESILEOS_HIDDEN_DIM", "128"))
KERNEL_DIM = int(os.getenv("RESILEOS_KERNEL_DIM", "1"))
MIN_TRAIN_STEPS = int(os.getenv("RESILEOS_MIN_TRAIN_STEPS", "5"))


class SubstrateContainer:
    """Module-level persistent model singleton for the substrate."""

    def __init__(self) -> None:
        torch.manual_seed(42)
        kernel = torch.zeros(HIDDEN_DIM, KERNEL_DIM)
        kernel[0, 0] = 1.0
        self.hidden_dim = HIDDEN_DIM
        self.kernel_dim = KERNEL_DIM
        self.geo_head = LowRankMetricHead(hidden_dim=HIDDEN_DIM)
        self.fep_head = VerifiableFEPReductionHead(
            hidden_dim=HIDDEN_DIM,
            L_H_kernel=kernel,
            rank=1,
        )
        trainable = (
            list(self.geo_head.parameters())
            + list(self.fep_head.parameters())
        )
        self.optimizer = torch.optim.AdamW(trainable, lr=1e-3)
        self.is_trained = False
        self.training_steps = 0
        self.last_train_metrics: dict | None = None

    def train_step(
        self, seq_len: int, g_field: float, epsilon: float, seed: int
    ) -> dict:
        self.optimizer.zero_grad()
        trunk = simulate_axiom_d(
            dim=self.hidden_dim, seq_len=seq_len,
            epsilon=epsilon, g_field=g_field, seed=seed,
        )
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
        metrics = {
            "geo": float(geo_loss.item()),
            "fep": float(fep_loss.item()),
            "total": float(total.item()),
        }
        self.last_train_metrics = metrics
        return metrics

    def save(self, path: Path) -> None:
        """Persist head weights, optimizer state, and training flags.

        The checkpoint is written atomically: a sibling .tmp file is
        written first, then renamed. A crash mid-write leaves the
        previous checkpoint intact.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        torch.save(
            {
                "geo_head": self.geo_head.state_dict(),
                "fep_head": self.fep_head.state_dict(),
                "optimizer": self.optimizer.state_dict(),
                "is_trained": self.is_trained,
                "training_steps": self.training_steps,
                "last_train_metrics": self.last_train_metrics,
                "hidden_dim": self.hidden_dim,
                "kernel_dim": self.kernel_dim,
            },
            tmp,
        )
        tmp.replace(path)

    def load(self, path: Path) -> bool:
        """Restore state if present. Returns True on success.

        Fails gracefully and logs a warning if the checkpoint is
        missing, corrupt, or incompatible with the current
        HIDDEN_DIM/KERNEL_DIM (e.g. after an env-var change).
        """
        if not path.exists():
            return False
        try:
            ckpt = torch.load(
                path, map_location="cpu", weights_only=False
            )
            ckpt_hidden = int(ckpt.get("hidden_dim", self.hidden_dim))
            if ckpt_hidden != self.hidden_dim:
                log.warning(
                    "Substrate checkpoint hidden_dim=%d != current %d; "
                    "ignoring checkpoint and starting fresh",
                    ckpt_hidden, self.hidden_dim,
                )
                return False
            self.geo_head.load_state_dict(ckpt["geo_head"])
            self.fep_head.load_state_dict(ckpt["fep_head"])
            self.optimizer.load_state_dict(ckpt["optimizer"])
            self.is_trained = bool(ckpt.get("is_trained", False))
            self.training_steps = int(ckpt.get("training_steps", 0))
            self.last_train_metrics = ckpt.get("last_train_metrics")
            log.info(
                "Substrate restored: trained=%s steps=%d",
                self.is_trained,
                self.training_steps,
            )
            return True
        except Exception as e:
            log.warning(
                "Substrate state unreadable, starting fresh: %s", e
            )
            return False


substrate_singleton = SubstrateContainer()
substrate_singleton.load(SUBSTRATE_STATE_PATH)


class VerificationRequest(BaseModel):
    hierarchical_states: list = Field(
        ..., description="[1, T, L, D] hierarchy of hidden states")
    velocity_direction: list = Field(
        ..., description="[1, T, D] velocity")
    g_field_sequence: list = Field(
        ..., description="[1, T, 1] coherence")


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
    """Health endpoint. Open (no auth): Docker HEALTHCHECK depends on it."""
    return {
        "hidden_dim": substrate_singleton.hidden_dim,
        "kernel_dim": substrate_singleton.kernel_dim,
        "is_trained": substrate_singleton.is_trained,
        "training_steps": substrate_singleton.training_steps,
        "min_train_steps": MIN_TRAIN_STEPS,
        "last_train_metrics": substrate_singleton.last_train_metrics,
        "bridge_locked": True,
        "state_path": str(SUBSTRATE_STATE_PATH),
    }


@app.post(
    "/api/v1/train_substrate",
    dependencies=[Depends(verify_api_key)],
)
def train_substrate(payload: TrainRequest):
    if payload.steps < 1 or payload.steps > 500:
        raise HTTPException(400, "steps must be in [1, 500]")
    history = []
    for i in range(payload.steps):
        eps = payload.base_epsilon / (1.0 + 0.3 * i)
        try:
            metrics = substrate_singleton.train_step(
                seq_len=payload.seq_len,
                g_field=payload.g_field,
                epsilon=eps,
                seed=payload.seed + i,
            )
        except Exception as e:
            raise HTTPException(500, f"training step {i} failed: {e}")
        history.append({"step": i, "epsilon": eps, **metrics})
    if substrate_singleton.training_steps >= MIN_TRAIN_STEPS:
        substrate_singleton.is_trained = True
    with _substrate_lock:
        try:
            substrate_singleton.save(SUBSTRATE_STATE_PATH)
        except Exception as e:
            log.warning("Substrate save failed: %s", e)
    return {
        "status": (
            "trained" if substrate_singleton.is_trained else "partial"
        ),
        "total_steps": substrate_singleton.training_steps,
        "is_trained": substrate_singleton.is_trained,
        "history": history,
    }


@app.post(
    "/api/v1/verify_manifold",
    dependencies=[Depends(verify_api_key)],
)
def verify_manifold(payload: VerificationRequest):
    if not substrate_singleton.is_trained:
        raise HTTPException(
            400,
            "Substrate is UNTRAINED. "
            f"completed_steps={substrate_singleton.training_steps}, "
            f"min={MIN_TRAIN_STEPS}. "
            "Call POST /api/v1/train_substrate first.",
        )
    try:
        h = torch.tensor(payload.hierarchical_states, dtype=torch.float32)
        x = torch.tensor(payload.velocity_direction, dtype=torch.float32)
        g = torch.tensor(payload.g_field_sequence, dtype=torch.float32)
        if h.dim() != 4 or h.size(0) != 1:
            raise ValueError(
                "hierarchical_states must be [1, T, L, D], "
                f"got {tuple(h.shape)}"
            )
        if h.size(-1) != substrate_singleton.hidden_dim:
            raise ValueError(
                "last dim must equal hidden_dim "
                f"({substrate_singleton.hidden_dim}), got {h.size(-1)}"
            )
        trunk = h.mean(dim=2)
        with torch.no_grad():
            _, geo_loss = substrate_singleton.geo_head(trunk, x)
            psi_s, fep_loss = substrate_singleton.fep_head(trunk, g)
        return {
            "status": "verified",
            "parallel_transport_penalty": float(geo_loss.item()),
            "fep_ode_alignment_loss": float(fep_loss.item()),
            "slow_subspace_trajectory": (
                psi_s.squeeze(0).squeeze(-1).tolist()
            ),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"manifold error: {e}")


@app.post(
    "/api/v1/sweep_epsilon",
    dependencies=[Depends(verify_api_key)],
)
def sweep_epsilon(payload: SweepRequest):
    if payload.metric not in ("rmse", "mse"):
        raise HTTPException(
            400,
            f"metric must be 'rmse' | 'mse', got {payload.metric!r}",
        )
    if len(payload.epsilons) < 2:
        raise HTTPException(400, "at least two epsilon values required")
    if any(e <= 0.0 for e in payload.epsilons):
        raise HTTPException(400, "epsilons must all be > 0")
    dim = substrate_singleton.hidden_dim
    if payload.mode == "simulate":
        def factory(eps: float) -> torch.Tensor:
            return simulate_axiom_d(
                dim=dim, seq_len=payload.seq_len,
                epsilon=eps, g_field=payload.g_field, seed=0,
            )
    elif payload.mode == "data":
        if payload.trajectory is None:
            raise HTTPException(
                400, "mode='data' requires a trajectory array"
            )
        arr = np.asarray(payload.trajectory, dtype=np.float32)
        if arr.ndim == 2:
            arr = arr[None, ...]
        if arr.ndim != 3:
            raise HTTPException(
                400,
                f"trajectory must be [T, D] or [K, T, D], got {arr.shape}",
            )
        if arr.shape[-1] != dim:
            raise HTTPException(
                400,
                f"trajectory last dim {arr.shape[-1]} != hidden_dim {dim}",
            )
        trunk_ref = torch.tensor(
            arr.mean(axis=0)[None, ...], dtype=torch.float32
        )

        def factory(eps: float) -> torch.Tensor:
            t = trunk_ref.clone()
            t[:, 0, 0] = 1.5 + eps
            return t
    else:
        raise HTTPException(
            400,
            f"mode must be 'simulate' | 'data', got {payload.mode!r}",
        )
    try:
        sample = factory(payload.epsilons[0])
        G = torch.ones(1, sample.shape[1], 1)
        result = substrate_singleton.fep_head.sweep_epsilon(
            factory, payload.epsilons, G, metric=payload.metric,
        )
    except Exception as e:
        raise HTTPException(500, f"sweep failed: {e}")
    slope = result["slope"]
    if payload.metric == "rmse":
        if 0.85 <= slope <= 1.15:
            verdict = (
                "consistent with linear O(ε) residual (RES-600 §4)"
            )
        elif slope < 0.85:
            verdict = "sub-linear; check trajectory or discretization"
        else:
            verdict = "super-linear; check discretization error dominance"
    else:
        if 1.85 <= slope <= 2.15:
            verdict = (
                "consistent with O(ε) residual under MSE metric"
            )
        else:
            verdict = "unexpected MSE scaling"
    return {
        "source": payload.mode,
        "dim": dim,
        "g_field": payload.g_field,
        **result,
        "verdict": verdict,
    }


# ═══════════════════════════════════════════════════════════════════════════
# leCore integration (capability router)
# ═══════════════════════════════════════════════════════════════════════════
_lecore = LeCoreClient()


class LeCoreRouteRequest(BaseModel):
    query: str


@app.get("/api/v1/lecore/health")
def lecore_health():
    """Health endpoint. Open (no auth): liveness probe depends on it."""
    try:
        return {"available": True, **_lecore.health()}
    except (LeCoreUnreachable, LeCoreError) as e:
        return {"available": False, "error": str(e)}


@app.post(
    "/api/v1/lecore/route",
    dependencies=[Depends(verify_api_key)],
)
def lecore_route(payload: LeCoreRouteRequest):
    query = payload.query.strip()
    if not query:
        raise HTTPException(400, "query is required")
    try:
        caps = _lecore.search(query)
    except (LeCoreUnreachable, LeCoreError) as e:
        return {"available": False, "error": str(e)}
    return {
        "available": True,
        "query": query,
        "capabilities": [
            {
                "name": c.name,
                "description": c.description,
                "score": c.score,
            }
            for c in caps
        ],
    }
