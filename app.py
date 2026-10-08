"""
FastAPI backend for the Titanos substrate.
Keeps the engine alive in-memory; exposes structured JSON.

Run:
    uvicorn app:app --port 8000 --reload
"""
import logging
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from titanos import Titanos, TitanosConfig  # noqa: E402

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("titanos.api")

app = FastAPI(title="Resileos-QAI Titanos Core Engine")

cfg = TitanosConfig(dim=10000, m=100, n=100, r=8, n_loops=12, seed=1337)
titan = Titanos(cfg)

STATE_FILE = ROOT / "titanos_live_state.json"
if STATE_FILE.exists():
    try:
        titan = Titanos.load(STATE_FILE)
        log.info("Loaded substrate state from %s", STATE_FILE)
    except Exception as e:
        log.warning("State file unreadable, starting fresh: %s", e)


# ── schemas ───────────────────────────────────────────────────────────────
class LearnRequest(BaseModel):
    subject: str
    relation: str
    obj: str


class QueryRequest(BaseModel):
    subject: str
    relation: str
    inverse: bool = False


class ChainRequest(BaseModel):
    start: str
    relations: list[str]


class BatchLearnRequest(BaseModel):
    facts: list[list[str]]


# ── endpoints ─────────────────────────────────────────────────────────────
@app.post("/api/v1/learn")
def learn_fact(payload: LearnRequest):
    s, r, o = payload.subject.strip(), payload.relation.strip(), payload.obj.strip()
    if not (s and r and o):
        raise HTTPException(status_code=400, detail="subject/relation/obj must be non-empty")
    try:
        titan.learn(s, r, o)
        titan.save(STATE_FILE)
        return {"status": "SUCCESS", "records": titan.stats()["facts"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/learn_batch")
def learn_batch(payload: BatchLearnRequest):
    if not payload.facts:
        raise HTTPException(status_code=400, detail="facts list is empty")
    added = 0
    for row in payload.facts:
        if len(row) != 3:
            continue
        s, r, o = (x.strip() for x in row)
        if not (s and r and o):
            continue
        titan.learn(s, r, o)
        added += 1
    if added:
        titan.save(STATE_FILE)
    return {"status": "SUCCESS", "added": added, "records": titan.stats()["facts"]}


@app.post("/api/v1/query")
def query_substrate(payload: QueryRequest):
    try:
        if payload.inverse:
            ans = titan.ask_inverse(payload.subject, payload.relation)
        else:
            ans = titan.ask(payload.subject, payload.relation)
        return {
            "value": ans.value,
            "confidence": float(ans.confidence),
            "status": ans.status,
            "mode": ans.mode,
            "loops": ans.loops,
            "reason": ans.reason,
            "trace": [
                {
                    "loop": h["loop"],
                    "scar": float(h["scar_energy"]),
                    "delta": float(h["delta"]),
                    "mu": h["mu"],
                    "vol_ok": h["volume_ok"],
                    "gate_state": h["gate_state"],
                }
                for h in ans.loop_history
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/chain")
def query_chain(payload: ChainRequest):
    if not payload.relations:
        raise HTTPException(status_code=400, detail="relations must be non-empty")
    try:
        ans = titan.chain(payload.start, payload.relations)
        return {
            "value": ans.value,
            "confidence": float(ans.confidence),
            "status": ans.status,
            "mode": ans.mode,
            "path": ans.path,
            "reason": ans.reason,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/stats")
def get_stats():
    return titan.stats()


@app.post("/api/v1/save")
def save_now():
    titan.save(STATE_FILE)
    return {"status": "SAVED", "path": str(STATE_FILE)}
