"""End-to-end smoke test: core → packet → adapter → validator → report."""
import json
from pathlib import Path

import numpy as np
import pytest

from resileos.abstention import AbstentionThresholds
from resileos.adapter import HDRIFTAdapter
from resileos.core import CoreConfig, ResidualCore
from resileos.moments import Seeds
from resileos.sigma import SigmaGate
from resileos.validation import HybridValidator, RunConfig


def _cfg():
    return RunConfig(
        packet_version="1.0.0",
        dim=128,
        seeds=Seeds.derived(42),
        N_warm=8,
        E_sat=10.0,
        E_sigma=10.0,
        tau_sat=0.9,
        tau_low=0.1,
        sigma1_k=3,
        X=0.0,
        Y=0,
        seed_list=(0, 1),
        drift_ratio_floor=0.0,
    )


def test_pipeline_runs_end_to_end():
    cfg = _cfg()
    core = ResidualCore(CoreConfig(m=16, n=16, r=4), seed=0)
    adapter = HDRIFTAdapter(dim=cfg.dim, seeds=cfg.seeds, drift_ratio_floor=0.0)
    th = AbstentionThresholds(E_sat=cfg.E_sat, tau_sat=cfg.tau_sat, tau_low=cfg.tau_low)
    validator = HybridValidator(cfg, adapter, th, sigma_gate=SigmaGate(cfg.E_sigma, cfg.sigma1_k))

    def packet_fn(seed, step):
        W = np.random.default_rng(seed * 1000 + step).standard_normal((16, 16))
        return core.step(W)

    def x_fn(seed, step):
        rng = np.random.default_rng(seed * 10000 + step)
        v = rng.standard_normal(cfg.dim)
        return v / (np.linalg.norm(v) + 1e-12)

    report = validator.run(
        packet_fn=packet_fn,
        x_fn=x_fn,
        horizon_len=6,
        recon_err_fn=lambda p: float(abs(p.F_res)),
    )

    assert "per_seed" in report
    assert "aggregate" in report
    assert "conformant" in report
    assert len(report["per_seed"]) == 2
    assert len(report["step_log"]) == 12  # 2 seeds × 6 steps

    # JSON-serializable
    json.dumps(report, default=float)
