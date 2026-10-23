#!/usr/bin/env python3
"""Coupled training probe (RES-319 §5).

Does the aggregate signal from a coupled EngineGroup separate facts,
compared to the uncoupled (kappa=0) control?

Design locked by RES-319 §5:
    Input:       R_shared + upper-tri M, NOT per-engine lat_s_k
    Ablation:    kappa=0 vs kappa=2, matched input dimension
    Gate:        feature-only nearest-centroid accuracy
    Next:        decoder path only if this gate passes

conditioning_delta = coupled_acc - uncoupled_acc.
Positive means the aggregate signal carries fact-level information that
coupling created.

Usage:
    PYTHONPATH=src python scripts/run_coupled_training_probe.py --feature-only
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from resileos.core import CoreConfig
from resileos.substrate.coupling import CouplingField
from resileos.substrate.engine_group import EngineGroup


def _aggregate_features(cp) -> np.ndarray:
    """R_shared + upper-tri coupling matrix. NOT per-engine lat_s_k.

    RES-319 §5: the per-engine latent block is dead under the current
    drive path (Cause A). The aggregate is the measured carrier input.
    """
    M = np.asarray(cp.coupling_matrix, dtype=np.float64)
    iu = np.triu_indices(M.shape[0], k=1)
    return np.concatenate(
        [[float(cp.R_shared)], M[iu]]
    ).astype(np.float64)


def _make_group(n: int, kappa: float, seed: int, m: int, r: int) -> EngineGroup:
    configs = [CoreConfig(m=m, n=m, r=r) for _ in range(n)]
    field = CouplingField(n_engines=n, kappa=kappa, seed=seed)
    return EngineGroup(configs, field, seed=seed)


def _load_facts(path: Path) -> list[tuple[str, str, str]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    facts = []
    for row in raw.get("facts", []):
        if isinstance(row, (list, tuple)) and len(row) == 3:
            s, r, o = (str(x).strip() for x in row)
            if s and r and o:
                facts.append((s, r, o))
    return facts


def _nearest_centroid_acc(X: np.ndarray, y: np.ndarray, n_classes: int) -> float:
    centroids = np.zeros((n_classes, X.shape[1]))
    for i in range(n_classes):
        mask = y == i
        if mask.sum() > 0:
            centroids[i] = X[mask].mean(axis=0)
    dists = np.linalg.norm(X[:, None, :] - centroids[None, :, :], axis=2)
    preds = np.argmin(dists, axis=1)
    return float((preds == y).mean())


def main() -> int:
    ap = argparse.ArgumentParser(description="Coupled training probe")
    ap.add_argument("--facts", type=str, default="configs/titanos-facts.json")
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--m", type=int, default=8)
    ap.add_argument("--r", type=int, default=4)
    ap.add_argument("--kappa-on", type=float, default=2.0)
    ap.add_argument("--steps", type=int, default=500)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--feature-only", action="store_true")
    ap.add_argument("--out", type=str, default="")
    args = ap.parse_args()

    facts_path = Path(args.facts)
    if not facts_path.exists():
        print(f"facts file not found: {facts_path}", file=sys.stderr)
        return 1
    facts = _load_facts(facts_path)
    if not facts:
        print(f"no facts loaded from {facts_path}", file=sys.stderr)
        return 1
    print(f"loaded {len(facts)} facts from {facts_path}")

    g_on = _make_group(args.n, args.kappa_on, args.seed, args.m, args.r)
    g_off = _make_group(args.n, 0.0, args.seed, args.m, args.r)

    rng = np.random.default_rng(args.seed)
    fact_drives = {
        fact: rng.standard_normal(args.n) * 0.5 for fact in facts
    }

    feats_on = []
    feats_off = []
    labels = []
    for t in range(args.steps):
        fact_idx = t % len(facts)
        fact = facts[fact_idx]
        drives = fact_drives[fact].copy()
        W = [
            np.random.default_rng(args.seed + t * args.n + i).standard_normal(
                (args.m, args.m)
            )
            for i in range(args.n)
        ]
        cp_on = g_on.step([w.copy() for w in W], drives=drives.copy())
        cp_off = g_off.step([w.copy() for w in W], drives=drives.copy())
        feats_on.append(_aggregate_features(cp_on))
        feats_off.append(_aggregate_features(cp_off))
        labels.append(fact_idx)

    X_on = np.stack(feats_on)
    X_off = np.stack(feats_off)
    y = np.asarray(labels)

    n_classes = len(facts)
    acc_on = _nearest_centroid_acc(X_on, y, n_classes)
    acc_off = _nearest_centroid_acc(X_off, y, n_classes)

    delta = acc_on - acc_off
    verdict = (
        "aggregate separates facts better under coupling"
        if delta > 0.05
        else "no measurable coupled advantage on fact separation"
    )

    report = {
        "mode": "feature_only",
        "n_engines": args.n,
        "kappa_on": args.kappa_on,
        "kappa_off": 0.0,
        "steps": args.steps,
        "n_facts": len(facts),
        "n_classes": n_classes,
        "feature_dim": int(X_on.shape[1]),
        "centroid_acc_coupled": acc_on,
        "centroid_acc_uncoupled": acc_off,
        "conditioning_delta": delta,
        "verdict": verdict,
        "notes": [
            "Feature-only probe: nearest-centroid accuracy on aggregate features.",
            "Input is R_shared + upper-tri M (RES-319 §5). Not per-engine lat_s_k.",
            "conditioning_delta = coupled_acc - uncoupled_acc. Positive means coupling helps.",
            "A decoder path is the next step only if this gate passes.",
        ],
    }

    out = (
        Path(args.out)
        if args.out
        else Path("artifacts/report_coupled_training_probe.json")
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))

    print(f"n_engines: {args.n}")
    print(f"kappa: {args.kappa_on} vs 0.0")
    print(f"facts: {len(facts)} ({n_classes} classes)")
    print(f"centroid acc coupled:   {acc_on:.4f}")
    print(f"centroid acc uncoupled: {acc_off:.4f}")
    print(f"conditioning_delta:     {delta:+.4f}")
    print(f"verdict: {verdict}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
