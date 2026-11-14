"""Lesson memory: one lesson line plus the residual packet hash, nothing else.

Stored only after a verified cycle (``review_proof_verified`` or a
verified Hades checkpoint). Raw traces, prompts, history, and facts are
never stored. The store is our own JSON file at the individual (persona)
tier, one file per owner under ``RESILEOS_LESSONS_DIR``; relevance uses a
VSA hypervector (``LatentHub.encode`` bundles of the lesson words), so no
outside embedding service is called.

A fresh control packet can load the most relevant lessons with
``load_into``. They go into ``guides_loaded`` / ``guide_bodies`` as
guide text only; history is not replayed and nothing is learned.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np

_HEX = re.compile(r"^[0-9a-f]{16,128}$")
_WORD = re.compile(r"[a-z0-9]{3,}")
MAX_LESSON = 240
MAX_ROWS = 500
_lock = threading.Lock()


def lessons_dir() -> Path:
    return Path(os.environ.get("RESILEOS_LESSONS_DIR", "data/lessons"))


def _owner_file(owner: str) -> Path:
    safe = hashlib.sha256(str(owner or "anon").encode()).hexdigest()[:24]
    return lessons_dir() / f"{safe}.json"


def _vector(text: str, dim: int = 256) -> np.ndarray:
    from resileos.latent_hub import LatentHub

    hub = LatentHub(dim=dim, seed=7)
    words = _WORD.findall(str(text or "").lower())
    if not words:
        return np.zeros(dim)
    total = np.sum([hub.encode(w) for w in words], axis=0)
    return np.sign(total)


def _verified(review: Any) -> bool:
    from resileos.kin.outer_legions import review_proof_verified

    if review_proof_verified(review):
        return True
    return bool(getattr(review, "verified", False)) and bool(getattr(review, "residual_packet_hash", None))


class LessonStore:
    def __init__(self, owner: str = "anon") -> None:
        self.owner = owner
        self.path = _owner_file(owner)

    def rows(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except ValueError:
            return []
        return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []

    def record(self, lesson: str, packet_hash: str, *, review: Any) -> dict[str, Any]:
        """Store one lesson after a verified cycle. Refuses otherwise."""
        from resileos.run_trace import emit

        text = " ".join(str(lesson or "").split())[:MAX_LESSON]
        if not _verified(review):
            emit("lesson", stored=False, packet_hash=packet_hash)
            return {"stored": False, "reason": "cycle not verified"}
        if not text or not _HEX.match(str(packet_hash or "")):
            return {"stored": False, "reason": "needs a lesson and a residual packet hash"}
        row = {"lesson": text, "packet_hash": str(packet_hash), "ts": int(time.time())}
        with _lock:
            rows = [r for r in self.rows() if r.get("packet_hash") != row["packet_hash"]]
            rows.append(row)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(rows[-MAX_ROWS:], ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)
        emit("lesson", stored=True, packet_hash=packet_hash)
        return {"stored": True, **row}

    def relevant(self, query: str, k: int = 3) -> list[dict[str, Any]]:
        q = _vector(query)
        if not q.any():
            return []
        scored = []
        for row in self.rows():
            v = _vector(row["lesson"])
            score = float(q @ v) / len(q)
            if score > 0:
                scored.append((score, row))
        scored.sort(key=lambda p: (-p[0], -p[1].get("ts", 0)))
        return [{"lesson": r["lesson"], "packet_hash": r["packet_hash"], "score": round(s, 4)} for s, r in scored[:k]]

    def load_into(self, packet: Any, query: str, k: int = 3) -> list[str]:
        """Put the k most relevant lessons on a fresh packet as guides. No history."""
        from resileos.run_trace import emit

        picked = self.relevant(query, k)
        ids = []
        for row in picked:
            gid = "lesson:" + row["packet_hash"][:12]
            if gid not in packet.guides_loaded:
                packet.guides_loaded.append(gid)
            packet.guide_bodies[gid] = row["lesson"]
            ids.append(gid)
        emit("lesson", loaded=len(ids))
        return ids


__all__ = ["LessonStore", "lessons_dir"]
