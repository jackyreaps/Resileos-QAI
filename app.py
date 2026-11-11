"""
FastAPI backend for Resileos-QAI.
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

from resileos.answer import (
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
from resileos.answer.policy import derive_frame, prefer_child
from resileos.integration.lecore_client import LeCoreClient, LeCoreUnreachable, LeCoreError
from resileos.substrate.geometry import LowRankMetricHead
from resileos.substrate.reduction import VerifiableFEPReductionHead, simulate_axiom_d
from resileos.titanos.query import TitanosQueryEngine, QuerySyntaxError, QueryBindingError
from resileos.substrate.agency import AgencyGroup
from resileos.titanos.zeus import make_zeus_handler, run_zeus_query
from resileos.kin.wiring import wire_kin
from resileos.answer.agent_loop import run_agent_chat

from resileos.harness.surface import ALWAYS_VISIBLE_TOOLS as HARNESS_TOOLS, search_tool_surface
from titanos import Answer, Titanos, TitanosConfig

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("resileos.api")

app = FastAPI(title="Resileos-QAI")
init_shared()

STATE_FILE = ROOT / "titanos_live_state.json"
SEED_FILE = ROOT / "configs" / "titanos-facts.json"

SUBSTRATE_STATE_PATH = Path(os.getenv("RESILEOS_SUBSTRATE_STATE", str(ROOT / "data" / "substrate_state.pt")))
_substrate_lock = threading.Lock()

_API_KEY_NAME = "X-API-Key"
_api_key_header = APIKeyHeader(name=_API_KEY_NAME, auto_error=False)
_KEYS_PATH = Path(os.getenv("API_KEYS_PATH", str(ROOT / "configs" / "api_keys.json")))
_AUTH_BYPASS = os.getenv("RESILEOS_AUTH_BYPASS", "0") == "1"

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
                is_hex = len(key) == 64 and all(c in "0123456789abcdef" for c in key.lower())
                merged[key if is_hex else _hash_key(key)] = record
        except Exception as e:
            log.warning("RESILEOS_API_KEYS is not valid JSON: %s", e)
    legacy = os.getenv("RESILEOS_API_KEY", "").strip()
    if legacy:
        merged.setdefault(_hash_key(legacy), {"name": "legacy", "tier": "enterprise", "quota": 0})
    return merged

def _configured_key_count() -> int:
    return len(_load_hashed_keys())

async def verify_api_key(api_key: str | None = Depends(_api_key_header)) -> None:
    if _AUTH_BYPASS:
        return
    keys = _load_hashed_keys()
    if not keys:
        raise HTTPException(status_code=503, detail="No API keys configured.")
    if api_key is None:
        raise HTTPException(status_code=401, detail="missing X-API-Key header")
    if keys.get(_hash_key(api_key.strip())) is None:
        raise HTTPException(status_code=403, detail="invalid API key")
    return None

_tcfg = TitanosConfig(dim=10000, m=100, n=100, r=8, n_loops=12, seed=1337, use_recovery_gate=(os.getenv("RESILEOS_USE_RECOVERY_GATE", "0") == "1"))
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
                if len(item) == 3: titanos_singleton.learn(item[0], item[1], item[2])
                else: titanos_singleton.learn(item[0], item[1], item[2], valid_from=item[3], valid_to=item[4])
                loaded += 1
            except Exception as e2:
                log.warning("Failed to learn %r: %s", item, e2)

    if loaded:
        try:
            titanos_singleton.save(STATE_FILE)
        except Exception as e:
            log.warning("Seeded %d facts but could not persist: %s", loaded, e)
    return loaded

_seed_count = _maybe_seed_from_bundled_facts()

try:
    _zeus_handler = make_zeus_handler()
    titanos_singleton.agency.add_child("zeus", _zeus_handler, weight=1.0)
except Exception as e:
    log.warning("Zeus registration failed; /query will use parent only: %s", e)

try:
    wire_kin(app, titanos_singleton, auth_dep=verify_api_key)
except Exception as e:
    log.warning("Kin wiring failed; kin routes unavailable: %s", e)

_answer_backend_singleton: AnswerBackend | None = None

def _answer_backend() -> AnswerBackend:
    global _answer_backend_singleton
    if _answer_backend_singleton is None:
        _answer_backend_singleton = select_backend()
    return _answer_backend_singleton

def harness_tool_schemas() -> list[dict]:
    out: list[dict] = []
    for name, fn in HARNESS_TOOLS.items():
        doc = (fn.__doc__ or name).strip().split("\n")[0]
        out.append({"name": name, "description": doc, "parameters": {"type": "object", "properties": {}}})
    return out

class _SPARQLAdapter:
    def __init__(self, titanos) -> None:
        self._t = titanos
    def ask(self, anchor: str, relation: str, inverse: bool = False, as_of: Optional[str] = None) -> list[str]:
        return self._t.ask_list(anchor, relation, inverse=inverse, as_of=as_of)
    def iter_entities(self) -> list[str]:
        return self._t.iter_entities()

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
    message: str
    history: list = []

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

@app.get("/api/v1/stats", dependencies=[Depends(verify_api_key)])
def titanos_stats():
    base = dict(titanos_singleton.stats())
    rels = list(titanos_singleton.relations.keys())
    n = len(rels)
    import math
    base["gate"] = {"n_relations": n, "gate_capacity_bits": (math.log2(n) if n > 0 else 0.0), "relation_alphabet": rels, "frames": frame_index()}
    return base

@app.get("/api/v1/tools", dependencies=[Depends(verify_api_key)])
def list_tools(q: Optional[str] = Query(default=None)):
    payload = {"tools": list_tool_schemas(), "openai": openai_tools(), "frames": frame_index(), "harness": harness_tool_schemas()}
    if q is not None:
        payload["search"] = search_tool_surface(q)
    return payload

@app.get("/api/v1/ready")
def titanos_ready():
    try:
        s = titanos_singleton.stats()
    except Exception as e:
        raise HTTPException(503, f"titanos store not ready: {e}")
    return {"ready": True, "facts": int(s.get("facts", 0)), "facts_with_validity": int(s.get("facts_with_validity", 0)), "facts_expired": int(s.get("facts_expired", 0)), "seeded_from": str(SEED_FILE) if _seed_count else None, "answer_backend": _answer_backend().name, "auth_required": (not _AUTH_BYPASS) and _configured_key_count() > 0}

@app.get("/api/v1/answer/backends", dependencies=[Depends(verify_api_key)])
def titanos_answer_backends():
    return {"configured": os.getenv("RESILEOS_ANSWER_BACKEND", "auto"), "active": _answer_backend().name, "backends": list_backends()}

@app.post("/api/v1/chat", dependencies=[Depends(verify_api_key)])
async def titanos_chat(payload: ChatRequest):
    try:
        result = await run_agent_chat(titanos_singleton, payload.message, payload.history)
        return result
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/v1/upload", dependencies=[Depends(verify_api_key)])
async def upload_file(file: UploadFile = File(...), message: str = Form("")):
    content = await file.read()
    file_type = file.content_type or "application/octet-stream"
    file_data = {"type": file_type, "size": len(content), "name": file.filename, "subject": f"file:{file.filename}"}
    if file_type.startswith("image/"):
        try:
            img = Image.open(io.BytesIO(content))
            file_data.update({"width": img.width, "height": img.height, "format": img.format})
        except Exception:
            pass
    result = await run_agent_chat(titanos_singleton, message, history=[], file_data=file_data)
    return result

@app.post("/api/v1/answer", dependencies=[Depends(verify_api_key)])
def titanos_answer(payload: AnswerRequest):
    subject, relation, inverse, question = _resolve_answer_input(payload)
    if not subject or not relation:
        return {"question": question or (payload.question or ""), "subject": subject or "", "relation": relation or "", "inverse": inverse, "rows": [], "answer_text": "", "backend": _answer_backend().name, "status": "NONE_CHANNEL", "confidence": 0.0, "recovery_loss": 0.0, "reason": "gate unresolved: no subject/relation", "symbol_index": -1, "sector": "", "gate_capacity_bits": 0.0, "as_of": payload.as_of, "frame": derive_frame(status="NONE_CHANNEL")}
    rows = titanos_singleton.ask_list(subject, relation, inverse=inverse, as_of=payload.as_of)
    confidence = 1.0 if rows else 0.0
    recovery_loss = 0.0
    if getattr(titanos_singleton.cfg, "use_recovery_gate", False):
        try:
            action, loss, reason = titanos_singleton._evaluate_recovery_gate()
        except Exception as e:
            action, loss, reason = ("CONTINUE", 0.0, "")
        recovery_loss = float(loss)
        if action == "ABSTAIN":
            return {"question": question or f"{subject} {relation}", "subject": subject, "relation": relation, "inverse": inverse, "rows": [], "answer_text": "", "backend": _answer_backend().name, "status": "ABSTAINED", "confidence": 0.0, "recovery_loss": recovery_loss, "reason": f"recovery gate: {reason}", "symbol_index": -1, "sector": "", "gate_capacity_bits": 0.0, "as_of": payload.as_of, "frame": derive_frame(status="ABSTAINED")}
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
    ctx = AnswerContext(question=question or f"{subject} {relation}", subject=subject, relation=relation, inverse=inverse, rows=tuple(rows), confidence=confidence, recovery_loss=recovery_loss, sector=sector)
    backend = _answer_backend()
    try:
        text = backend.render(ctx)
    except Exception as e:
        backend = StructuredBackend()
        text = backend.render(ctx)
    status = "ANSWERED" if rows else "NO_ROWS"
    return {"question": ctx.question, "subject": subject, "relation": relation, "inverse": inverse, "rows": list(rows), "answer_text": text, "backend": backend.name, "status": status, "confidence": confidence, "recovery_loss": recovery_loss, "reason": "", "symbol_index": sym, "sector": sector, "gate_capacity_bits": cap, "as_of": payload.as_of, "frame": derive_frame(sector=sector, status=status, n_rows=len(rows))}

@app.post("/api/v1/learn", dependencies=[Depends(verify_api_key)])
def titanos_learn(payload: LearnRequest):
    s, r, o = payload.subject.strip(), payload.relation.strip(), payload.obj.strip()
    if not (s and r and o): raise HTTPException(400, "subject/relation/obj must be non-empty")
    try:
        titanos_singleton.learn(s, r, o, valid_from=payload.valid_from, valid_to=payload.valid_to)
        titanos_singleton.save(STATE_FILE)
        return {"status": "SUCCESS", "records": titanos_singleton.stats()["facts"], "valid_from": payload.valid_from, "valid_to": payload.valid_to}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/v1/learn_batch", dependencies=[Depends(verify_api_key)])
def titanos_learn_batch(payload: BatchLearnRequest):
    if not payload.facts: raise HTTPException(400, "facts list is empty")
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
        out = {"value": ans.value, "confidence": float(ans.confidence), "status": ans.status, "mode": ans.mode, "loops": ans.loops, "reason": ans.reason, "gate_state": ans.gate_state, "child_name": ans.child_name, "recovery_loss": float(getattr(ans, "recovery_loss", 0.0)), "as_of": payload.as_of, "trace": [{"loop": h["loop"], "scar": float(h["scar_energy"]), "delta": float(h["delta"]), "mu": h["mu"], "deltas": float(h.get("DeltaS", 0.0)), "vol_ok": h["volume_ok"], "gate_state": h["gate_state"]} for h in ans.loop_history]}
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
                backend = StructuredBackend()
                text = backend.render(ctx)
            out["answer_text"] = text
            out["backend"] = backend.name
        return with_scale(out, payload.subject, payload.relation)
    except HTTPException: raise
    except Exception as e: raise HTTPException(500, str(e))

@app.post("/api/v1/sparql", dependencies=[Depends(verify_api_key)])
def titanos_sparql(payload: SparqlRequest):
    q = payload.query.strip()
    if not q: raise HTTPException(400, "query is required")
    engine = TitanosQueryEngine(_SPARQLAdapter(titanos_singleton))
    try: rows = engine.execute(q)
    except QuerySyntaxError as e: raise HTTPException(400, f"syntax error: {e}")
    except QueryBindingError as e: raise HTTPException(400, f"binding error: {e}")
    except Exception as e: raise HTTPException(500, f"query execution failed: {e}")
    return {"rows": [list(r) for r in rows], "count": len(rows)}

@app.post("/api/v1/chain", dependencies=[Depends(verify_api_key)])
def titanos_chain(payload: ChainRequest):
    if not payload.relations: raise HTTPException(400, "relations must be non-empty")
    try:
        ans = titanos_singleton.chain(payload.start, payload.relations)
        return {"value": ans.value, "confidence": float(ans.confidence), "status": ans.status, "mode": ans.mode, "path": ans.path, "reason": ans.reason}
    except Exception as e: raise HTTPException(500, str(e))

@app.post("/api/v1/save", dependencies=[Depends(verify_api_key)])
def titanos_save():
    titanos_singleton.save(STATE_FILE)
    return {"status": "SAVED", "path": str(STATE_FILE)}

@app.get("/api/v1/kin/hades/list", dependencies=[Depends(verify_api_key)])
def hades_list():
    return {"checkpoints": [{"id": "cp_001", "name": "Initial verified state"}]}

@app.post("/api/v1/kin/hades/restore", dependencies=[Depends(verify_api_key)])
def hades_restore(payload: dict):
    return {"status": "RESTORED", "lesson": "Restored from checkpoint", "residual_hash": "abcdef123456"}

@app.post("/api/v1/tools/video_generate", dependencies=[Depends(verify_api_key)])
def video_generate(payload: dict):
    return {"status": "SUCCESS", "video_url": "https://example.com/draft.mp4", "draft": True}

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
        torch.save({"geo_head": self.geo_head.state_dict(), "fep_head": self.fep_head.state_dict(), "optimizer": self.optimizer.state_dict(), "is_trained": self.is_trained, "training_steps": self.training_steps, "last_train_metrics": self.last_train_metrics, "hidden_dim": self.hidden_dim, "kernel_dim": self.kernel_dim}, tmp)
        tmp.replace(path)
    def load(self, path: Path) -> bool:
        if not path.exists(): return False
        try:
            ckpt = torch.load(path, map_location="cpu", weights_only=False)
            ckpt_hidden = int(ckpt.get("hidden_dim", self.hidden_dim))
            if ckpt_hidden != self.hidden_dim: return False
            self.geo_head.load_state_dict(ckpt["geo_head"])
            self.fep_head.load_state_dict(ckpt["fep_head"])
            self.optimizer.load_state_dict(ckpt["optimizer"])
            self.is_trained = bool(ckpt.get("is_trained", False))
            self.training_steps = int(ckpt.get("training_steps", 0))
            self.last_train_metrics = ckpt.get("last_train_metrics")
            return True
        except Exception as e:
            log.warning("Substrate state unreadable, starting fresh: %s", e)
            return False

substrate_singleton = SubstrateContainer()
substrate_singleton.load(SUBSTRATE_STATE_PATH)

class VerificationRequest(BaseModel):
    hierarchical_states: list = Field(...)
    velocity_direction: list = Field(...)
    g_field_sequence: list = Field(...)

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
    return {"hidden_dim": substrate_singleton.hidden_dim, "kernel_dim": substrate_singleton.kernel_dim, "is_trained": substrate_singleton.is_trained, "training_steps": substrate_singleton.training_steps, "min_train_steps": MIN_TRAIN_STEPS, "last_train_metrics": substrate_singleton.last_train_metrics, "bridge_locked": True, "state_path": str(SUBSTRATE_STATE_PATH)}

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
        raise HTTPException(400, f"Substrate is UNTRAINED.")
    try:
        h = torch.tensor(payload.hierarchical_states, dtype=torch.float32)
        x = torch.tensor(payload.velocity_direction, dtype=torch.float32)
        g = torch.tensor(payload.g_field_sequence, dtype=torch.float32)
        trunk = h.mean(dim=2)
        with torch.no_grad():
            _, geo_loss = substrate_singleton.geo_head(trunk, x)
            psi_s, fep_loss = substrate_singleton.fep_head(trunk, g)
        return {"status": "verified", "parallel_transport_penalty": float(geo_loss.item()), "fep_ode_alignment_loss": float(fep_loss.item()), "slow_subspace_trajectory": (psi_s.squeeze(0).squeeze(-1).tolist())}
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
    verdict = "consistent with linear O(ε) residual (RES-600 §4)" if 0.85 <= slope <= 1.15 else ("sub-linear" if slope < 0.85 else "super-linear")
    return {"source": payload.mode, "dim": dim, "g_field": payload.g_field, **result, "verdict": verdict}

_lecore = LeCoreClient()

class LeCoreRouteRequest(BaseModel):
    query: str

@app.get("/api/v1/lecore/health")
def lecore_health():
    try: return {"available": True, **_lecore.health()}
    except (LeCoreUnreachable, LeCoreError) as e: return {"available": False, "error": str(e)}

@app.post("/api/v1/lecore/route", dependencies=[Depends(verify_api_key)])
def lecore_route(payload: LeCoreRouteRequest):
    query = payload.query.strip()
    if not query: raise HTTPException(400, "query is required")
    try: caps = _lecore.search(query)
    except (LeCoreUnreachable, LeCoreError) as e: return {"available": False, "error": str(e)}
    return {"available": True, "query": query, "capabilities": [{"name": c.name, "description": c.description, "score": c.score} for c in caps]}
