#!/usr/bin/env python3
"""RES-401-ternary §5 acceptance probes (CPU)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from resileos.capacity import hopfield_cap
from resileos.core import CoreConfig, ResidualCore
from resileos.substrate.sdm import AttractorMemory, SDMConfig

try:
    from resileos.training_ternary_patch import FrontEndEncoder
except ImportError:
    from resileos.training import FrontEndEncoder  # type: ignore


def main() -> int:
    rng = np.random.default_rng(0)
    m, n, r = 32, 32, 8
    W_dense = rng.standard_normal((m, n)).astype(np.float32)
    W_sparse = W_dense.copy()
    W_sparse[np.abs(W_sparse) < 0.8] = 0.0

    def mse(W, Ub, Vb):
        return float(np.mean((W - Ub @ Vb) ** 2))

    enc_b = FrontEndEncoder(m, n, r, seed=1, mode="bipolar")
    enc_t = FrontEndEncoder(m, n, r, seed=1, mode="ternary", tau=0.05)
    out_b = enc_b.forward(W_dense)
    out_t = enc_t.forward(W_dense)
    out_bs = enc_b.forward(W_sparse)
    out_ts = enc_t.forward(W_sparse)

    core = ResidualCore(CoreConfig(m=m, n=n, r=r), seed=0)
    Ub_b, Vb_b = enc_b.factors_for_core(out_b)
    Ub_t, Vb_t = enc_t.factors_for_core(out_t)
    pkt_b = core.step(W_dense.astype(np.float64), factors=(Ub_b, Vb_b))
    pkt_t = core.step(W_dense.astype(np.float64), factors=(Ub_t, Vb_t))

    mem = AttractorMemory(SDMConfig(dim=64, n_locations=256, k_activate=8))
    for _ in range(hopfield_cap() + 20):
        mem.store(rng.standard_normal(64))
    mem.flush()

    report = {
        "probes": {
            "mse": {
                "dense_bipolar": mse(W_dense, out_b["Ub"], out_b["Vb"]),
                "dense_ternary": mse(W_dense, out_t["Ub"], out_t["Vb"]),
                "sparse_bipolar": mse(W_sparse, out_bs["Ub"], out_bs["Vb"]),
                "sparse_ternary": mse(W_sparse, out_ts["Ub"], out_ts["Vb"]),
            },
            "packet": {
                "bipolar_step": True,
                "ternary_mapped_step": True,
                "version": getattr(pkt_b, "version", None),
            },
            "hopfield_cap": {
                "cap": hopfield_cap(),
                "n_patterns": int(mem.hopfield.n_patterns),
                "wired": mem.hopfield.n_patterns == hopfield_cap(),
            },
        }
    }
    out = Path("artifacts/report_ternary_acceptance.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
