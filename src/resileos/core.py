"""
RES-303 trigger 3: k consecutive volume failures escalate through the
sigma-1 gate to CLEANUP, not through the abstention machine to ABSTAIN.
"""
import numpy as np

from resileos.adapter import HDRIFTAdapter
from resileos.abstention import AbstentionThresholds
from resileos.moments import Seeds
from resileos.sigma import SigmaAction
from resileos.validation import HybridValidator, RunConfig


def _packet(volume_ok: bool, scar: float = 0.0, mu: int = 0):
    rng = np.random.default_rng(0)
    r, m, n = 4, 8, 8
    return {
        "Ub": np.sign(rng.standard_normal((m, r))),
        "Vb": np.sign(rng.standard_normal((n, r))),
        "row_s_k": np.zeros(m, dtype=np.int16),
        "col_s_k": np.zeros(n, dtype=np.int16),
        "lat_s_k": np.zeros(r, dtype=np.int16),
        "Lambda": np.eye(r, dtype=np.float32) * scar,
        "mu": mu,
        "DeltaS": 0.5,
        "F_res": 0.0,
        "volume": 1.0,
        "volume_ok": volume_ok,
        "rank": 1,
        "schedule_index": 0,
    }


def _config():
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
        seed_list=(0,),
        drift_ratio_floor=0.0,
    )


def _x(seed, t):
    rng = np.random.default_rng(seed * 1000 + t)
    v = rng.standard_normal(128)
    return v / (np.linalg.norm(v) + 1e-12)


def test_consecutive_volume_failures_escalate_to_cleanup():
    cfg = _config()
    adapter = HDRIFTAdapter(dim=cfg.dim, seeds=cfg.seeds, drift_ratio_floor=0.0)
    th = AbstentionThresholds(E_sat=cfg.E_sat, tau_sat=cfg.tau_sat, tau_low=cfg.tau_low)

    validator = HybridValidator(cfg, adapter, th)

    def packet_fn(seed, t):
        return _packet(volume_ok=False)

    report = validator.run(
        packet_fn=packet_fn,
        x_fn=_x,
        horizon_len=6,
        recon_err_fn=lambda p: 0.05,
    )

    states = [r["gate_state"] for r in report["step_log"]]
    actions = [r["sigma1_action"] for r in report["step_log"]]

    # First k steps: streak <= k, gate has not fired yet.
    # The abstention machine handles volume_ok == False → ABSTAIN.
    assert states[0] == "ABSTAIN"
    assert states[1] == "ABSTAIN"
    assert states[2] == "ABSTAIN"
    assert actions[0] == "NONE"
    assert actions[1] == "NONE"
    assert actions[2] == "NONE"

    # Step k (index 3): streak > k → sigma-1 fires with CLEANUP,
    # and CLEANUP takes precedence over ABSTAIN.
    assert states[3] == "CLEANUP"
    assert actions[3] == SigmaAction.CLEANUP.value

    # Keeps firing while volume stays bad.
    assert states[4] == "CLEANUP"
    assert states[5] == "CLEANUP"


def test_recovery_resets_volume_streak():
    cfg = _config()
    adapter = HDRIFTAdapter(dim=cfg.dim, seeds=cfg.seeds, drift_ratio_floor=0.0)
    th = AbstentionThresholds(E_sat=cfg.E_sat, tau_sat=cfg.tau_sat, tau_low=cfg.tau_low)
    validator = HybridValidator(cfg, adapter, th)

    # Two failures, one success, then two more failures. Streak must reset.
    pattern = [False, False, True, False, False]

    def packet_fn(seed, t):
        return _packet(volume_ok=pattern[t])

    report = validator.run(
        packet_fn=packet_fn,
        x_fn=_x,
        horizon_len=len(pattern),
        recon_err_fn=lambda p: 0.05,
    )

    actions = [r["sigma1_action"] for r in report["step_log"]]
    # No CLEANUP anywhere: streak never exceeds k=3.
    assert all(a == "NONE" for a in actions)
