#!/usr/bin/env python3
"""Coupled vs uncoupled signal-presence probe (no decoder, no carrier).

Same N engines, same concatenated feature dimension, same seeds.
Only difference: kappa=0 (uncoupled) vs kappa>0 (coupled).

Disaggregates MI by feature group:
    lat_s_k (propagation) | R_shared (aggregation) | coupling_matrix (cross-state)

Also reports the §3a mechanism check: is lat_s_k constant, topic-clustered,
or noisy under the current drive schedule?

Usage:
    PYTHONPATH=src python scripts/run_coupled_signal_probe.py
    PYTHONPATH=src python scripts/run_coupled_signal_probe.py --steps 2000 --n 3
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np

from resileos.core import CoreConfig
from resileos.substrate.coupling import CouplingField
from resileos.substrate.engine_group import EngineGroup


def _feat_from_coupled(cp) -> np.ndarray:
    """Fixed-layout vector: concat lat_s_k over engines + R + upper-tri M."""
    parts = []
    for p in cp.packets:
        parts.append(np.asarray(p.lat_s_k, dtype=np.float64).ravel())
        parts.append(
            np.array(
                [float(p.F_res), float(p.DeltaS), float(p.mu)],
                dtype=np.float64,
            )
        )
    parts.append(np.array([float(cp.R_shared)], dtype=np.float64))
    M = np.asarray(cp.coupling_matrix, dtype=np.float64)
    iu = np.triu_indices(M.shape[0], k=1)
    parts.append(M[iu])
    return np.concatenate(parts)


def _scalar_mi(x: np.ndarray, y: np.ndarray, n_bins: int = 8) -> float:
    """Histogram MI between 1-D continuous x and discrete y (nats)."""
    x = np.asarray(x, dtype=np.float64).ravel()
    y = np.asarray(y).astype(int)
    edges = np.unique(np.quantile(x, np.linspace(0, 1, n_bins + 1)))
    if edges.size < 3:
        return 0.0
    xb = np.digitize(x, edges[1:-1])
    n = len(x)
    joint: dict[tuple[int, int], int] = {}
    for a, b in zip(xb, y):
        joint[(int(a), int(b))] = joint.get((int(a), int(b)), 0) + 1
    px = Counter(xb.tolist())
    py = Counter(y.tolist())
    mi = 0.0
    for (a, b), c in joint.items():
        pab = c / n
        pa = px[a] / n
        pb = py[b] / n
        mi += pab * np.log((pab + 1e-300) / (pa * pb + 1e-300))
    return max(float(mi), 0.0)


def _histogram_mi(x: np.ndarray, y: np.ndarray, n_bins: int = 8) -> float:
    """Mean per-dimension MI."""
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        return _scalar_mi(x, y, n_bins)
    mis = [_scalar_mi(x[:, j], y, n_bins) for j in range(x.shape[1])]
    return float(np.mean(mis))


def _make_group(n: int, kappa: float, seed: int, m: int, r: int) -> EngineGroup:
    configs = [CoreConfig(m=m, n=m, r=r) for _ in range(n)]
    field = CouplingField(n_engines=n, kappa=kappa, seed=seed)
    return EngineGroup(configs, field, seed=seed)


def _mechanism_stats(lat_streams: list, n_topics: int) -> dict:
    """§3a diagnostic: is lat_s_k constant, topic-clustered, or noisy?

    Cause A — std≈0, unique_rows=1: drive does not reach lat_s_k.
    Cause B — std>0, unique_rows≈T: latents vary, independent of topic.
    Cause C — std>0, unique_rows≈n_topics: cluster by topic; probe bug
              (MI estimator or bin count).
    """
    arr = np.array(lat_streams)  # (T, N, r)
    T = arr.shape[0]
    per_engine = []
    for i in range(arr.shape[1]):
        block = arr[:, i, :]
        std = float(block.std(axis=0).mean())
        uniq = int(len(np.unique(block, axis=0)))
        per_engine.append({"engine": i, "mean_std": std, "unique_rows": uniq})
    if all(e["mean_std"] < 1e-9 and e["unique_rows"] == 1 for e in per_engine):
        cause = "A"
        reading = "latents constant; drive does not reach lat_s_k"
    elif all(e["unique_rows"] > 0.9 * T for e in per_engine):
        cause = "B"
        reading = "latents vary but independent of topic"
    elif all(
        2 <= e["unique_rows"] <= max(16, 2 * n_topics) for e in per_engine
    ):
        cause = "C"
        reading = "latents cluster by topic; probe likely buggy"
    else:
        cause = "mixed"
        reading = "per-engine behaviour differs; inspect per_engine reading list"
    return {"cause": cause, "reading": reading, "per_engine": per_engine}


def main() -> int:
    ap = argparse.ArgumentParser(description="Coupled vs uncoupled MI probe")
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--steps", type=int, default=2000)
    ap.add_argument("--m", type=int, default=8)
    ap.add_argument("--r", type=int, default=4)
    ap.add_argument("--kappa-on", type=float, default=2.0)
    ap.add_argument("--n-topics", type=int, default=4)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--bins", type=int, default=8)
    ap.add_argument("--out", type=str, default="")
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    g_on = _make_group(args.n, args.kappa_on, args.seed, args.m, args.r)
    g_off = _make_group(args.n, 0.0, args.seed, args.m, args.r)

    feats_on = []
    feats_off = []
    lat_streams_on: list[list[np.ndarray]] = []
    lat_streams_off: list[list[np.ndarray]] = []
    labels = []

    for t in range(args.steps):
        topic = int(t % args.n_topics)
        drives = np.zeros(args.n)
        drives[topic % args.n] = 0.5 + 0.1 * topic
        drives[(topic + 1) % args.n] = -0.3
        W = [
            rng.standard_normal((args.m, args.m)) * (1.0 + 0.05 * topic)
            for _ in range(args.n)
        ]
        cp_on = g_on.step([w.copy() for w in W], drives=drives.copy())
        cp_off = g_off.step([w.copy() for w in W], drives=drives.copy())
        feats_on.append(_feat_from_coupled(cp_on))
        feats_off.append(_feat_from_coupled(cp_off))
        lat_streams_on.append(
            [
                np.asarray(p.lat_s_k, dtype=np.float64).ravel()
                for p in cp_on.packets
            ]
        )
        lat_streams_off.append(
            [
                np.asarray(p.lat_s_k, dtype=np.float64).ravel()
                for p in cp_off.packets
            ]
        )
        labels.append(topic)

    X_on = np.stack(feats_on)
    X_off = np.stack(feats_off)
    y = np.asarray(labels)
    assert X_on.shape == X_off.shape

    n, r = args.n, args.r
    eng_dim = n * (r + 3)
    r_idx = eng_dim
    n_pairs = n * (n - 1) // 2

    lat_cols = []
    for i in range(n):
        base = i * (r + 3)
        lat_cols.extend(range(base, base + r))
    lat_cols = np.array(lat_cols, dtype=int)
    M_cols = np.arange(r_idx + 1, r_idx + 1 + n_pairs)

    def group_mi(X, cols):
        if cols.size == 0:
            return 0.0
        return _histogram_mi(X[:, cols], y, n_bins=args.bins)

    mi_lat_on = group_mi(X_on, lat_cols)
    mi_lat_off = group_mi(X_off, lat_cols)
    mi_R_on = _scalar_mi(X_on[:, r_idx], y, n_bins=args.bins)
    mi_R_off = _scalar_mi(X_off[:, r_idx], y, n_bins=args.bins)
    mi_M_on = group_mi(X_on, M_cols)
    mi_M_off = group_mi(X_off, M_cols)
    mi_on = _histogram_mi(X_on, y, n_bins=args.bins)
    mi_off = _histogram_mi(X_off, y, n_bins=args.bins)

    delta = mi_on - mi_off
    delta_R = mi_R_on - mi_R_off
    delta_lat = mi_lat_on - mi_lat_off
    delta_M = mi_M_on - mi_M_off

    score = max(delta, delta_R, delta_lat, delta_M)
    if score > 0.1:
        verdict = "coupled carries more task signal — training probe justified"
    elif min(delta, delta_R, delta_lat, delta_M) < -0.05:
        verdict = "coupling destroys signal — debug cross terms"
    else:
        verdict = "coupling adds no measurable task information (at this scale)"

    if delta_lat > 0.1:
        rec = "per-engine lat_s_k"
    elif delta_R > 0.1:
        rec = "aggregate R_shared (and optionally M)"
    else:
        rec = "no clear coupled advantage"

    mech_on = _mechanism_stats(lat_streams_on, args.n_topics)
    mech_off = _mechanism_stats(lat_streams_off, args.n_topics)

    report = {
        "probe": "coupled_signal_presence",
        "n_engines": args.n,
        "steps": args.steps,
        "kappa_on": args.kappa_on,
        "kappa_off": 0.0,
        "feature_dim": int(X_on.shape[1]),
        "n_topics": args.n_topics,
        "MI_coupled_nats": mi_on,
        "MI_uncoupled_nats": mi_off,
        "delta_MI_nats": delta,
        "MI_R_coupled_nats": mi_R_on,
        "MI_R_uncoupled_nats": mi_R_off,
        "delta_MI_R_nats": delta_R,
        "MI_lat_coupled_nats": mi_lat_on,
        "MI_lat_uncoupled_nats": mi_lat_off,
        "delta_MI_lat_nats": delta_lat,
        "MI_M_coupled_nats": mi_M_on,
        "MI_M_uncoupled_nats": mi_M_off,
        "delta_MI_M_nats": delta_M,
        "lat_mechanism_coupled": mech_on,
        "lat_mechanism_uncoupled": mech_off,
        "carrier_input_recommendation": rec,
        "verdict": verdict,
        "notes": [
            "Ablation is kappa only; input dimension matched.",
            "No carrier, no decoder — signal presence only.",
            "Target label = topic index used to schedule drives.",
            "Disaggregated MI: lat=propagation, R=aggregation, M=cross-state.",
            "§3a mechanism check: see lat_mechanism_coupled.cause (A/B/C).",
        ],
    }

    out = (
        Path(args.out)
        if args.out
        else Path("artifacts/report_coupled_signal_probe.json")
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))

    print(f"feature_dim (matched): {X_on.shape[1]}")
    print(f"MI coupled: {mi_on:.4f} nats")
    print(f"MI uncoupled: {mi_off:.4f} nats")
    print(f"ΔMI mean-dim: {delta:+.4f}")
    print(f"ΔMI lat_s_k: {delta_lat:+.4f} (propagation)")
    print(f"ΔMI R_shared: {delta_R:+.4f} (aggregation)")
    print(f"ΔMI M matrix: {delta_M:+.4f} (cross-state)")
    print(
        f"§3a mechanism (coupled): cause={mech_on['cause']} "
        f"— {mech_on['reading']}"
    )
    for e in mech_on["per_engine"]:
        print(
            f"  engine {e['engine']}: mean_std={e['mean_std']:.6f} "
            f"unique_rows={e['unique_rows']}"
        )
    print(f"verdict: {verdict}")
    print(f"carrier input: {rec}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
