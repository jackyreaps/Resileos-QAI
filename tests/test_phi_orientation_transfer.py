"""Verify φ-compress orientation transfer (RES-501 roadmap item 1)."""
from __future__ import annotations

import numpy as np

from resileos.phi_compress import contract_rank
from resileos.pipeline import LanguagePipeline, PipelineConfig


def _cfg(**kw):
    base = dict(
        dim=256,
        vocab_size=64,
        max_positions=64,
        m=16,
        n=16,
        r=8,
        n_residual_layers=4,
        reaper_n_saved=4,
        phi_compress_enabled=True,
        phi_compress_warmup=0,
        phi_compress_min_R=0.0,
        phi_compress_min_rank=4,
        oscillator_kappa=1.0,
        oscillator_alpha=0.5,
        oscillator_dt=0.1,
        seed=0,
    )
    base.update(kw)
    return PipelineConfig(**base)


def test_orientation_transfer_preserves_kept_theta_omega():
    p = LanguagePipeline(_cfg())
    p.step([1, 2])
    old_r = p.core.cfg.r
    new_r = contract_rank(old_r, min_rank=4)
    assert new_r < old_r

    p.field.theta = np.linspace(-0.05, 0.05, old_r)
    p.field.omega = np.linspace(0.5, 1.5, old_r)
    theta_ref = float(np.angle(np.mean(np.exp(1j * p.field.theta))))
    dtheta = np.sign(np.angle(np.exp(1j * (p.field.theta - theta_ref))))
    dtheta[dtheta == 0] = 1.0
    n_drop = old_r - new_r
    order = np.argsort(np.abs(dtheta))
    drop_set = set(int(i) for i in order[:n_drop])
    keep = [i for i in range(old_r) if i not in drop_set]
    theta_keep = p.field.theta[keep].copy()
    omega_keep = p.field.omega[keep].copy()

    p._last_R = 0.95
    p._maybe_contract()

    assert p.core.cfg.r == new_r
    assert p.field.r == new_r
    np.testing.assert_allclose(p.field.theta, theta_keep, atol=1e-12)
    np.testing.assert_allclose(p.field.omega, omega_keep, atol=1e-12)
    assert p._orientation is not None
    assert p._orientation.shape == (new_r,)
    assert len(p.stats()["compressions"]) >= 1
