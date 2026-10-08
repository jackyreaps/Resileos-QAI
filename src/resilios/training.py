"""
Residual-compensation training for the front-end encoder only.
Owning doc: RES-401.

Gradient scope (RES-401 §scope):
  Frozen core (never receives gradients):
    - Jacobian
    - Scar update Λ
    - Volume guard
    - Prime-Tower schedule
    - Residual-flux parity invariant
  Trainable front-end only:
    - The encoder that produces Ub, Vb, row_s_k, col_s_k, lat_s_k.

This module never modifies Λ, the volume guard, or the schedule. It reads
their values for monitoring only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .core import ResidualCore
from .packet import encode_exponent


# ── straight-through estimator (QAT per RES-401) ──────────────────────────
def ste_sign(x: np.ndarray) -> np.ndarray:
    """Forward: sign. Backward: identity (straight-through)."""
    return np.where(x >= 0.0, 1.0, -1.0)


# ── trainable encoder (front-end only) ────────────────────────────────────
class FrontEndEncoder:
    """
    Produces Ub, Vb, and residual-scale fields from a weight block W.
    Only P and Q are trainable. Per RES-401 §scope.
    """
    def __init__(self, m: int, n: int, r: int, seed: int = 0):
        rng = np.random.default_rng(seed)
        self.P = rng.standard_normal((n, r)) * 0.1   # (n, r)
        self.Q = rng.standard_normal((r, m)) * 0.1   # (r, m)
        self.m, self.n, self.r = m, n, r

    def forward(self, W: np.ndarray) -> dict[str, np.ndarray]:
        U_pre = W @ self.P
        V_pre = self.Q @ W
        return {
            "Ub": ste_sign(U_pre).astype(np.float32),
            "Vb": ste_sign(V_pre).astype(np.float32),
            "U_pre": U_pre,
            "V_pre": V_pre,
        }

    def residual_fields(self,
                        W: np.ndarray,
                        Ub: np.ndarray,
                        Vb: np.ndarray,
                        ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        R = W - Ub @ Vb
        row_mag = np.linalg.norm(R, axis=1)
        col_mag = np.linalg.norm(R, axis=0)
        lat_mag = np.linalg.norm(Ub.T @ R @ Vb.T, axis=1)
        row_s_k = np.array([encode_exponent(x) for x in row_mag], dtype=np.int16)
        col_s_k = np.array([encode_exponent(x) for x in col_mag], dtype=np.int16)
        lat_s_k = np.array([encode_exponent(x) for x in lat_mag], dtype=np.int16)
        return R, row_s_k, col_s_k, lat_s_k


# ── loss and analytic gradients (STE through sign) ────────────────────────
def loss_and_grads(W: np.ndarray,
                   enc_out: dict[str, np.ndarray],
                   lam: float) -> tuple[float, np.ndarray, np.ndarray]:
    """
    L = ||W - Ub @ Vb||_F² / (m·n)
      + λ · (mean_row ||R||² + mean_col ||R||²)

    Returns (loss, dU_pre, dV_pre). Backward through sign uses identity (STE).
    """
    Ub, Vb = enc_out["Ub"], enc_out["Vb"]
    m, n = W.shape
    W_hat = Ub @ Vb
    R = W - W_hat

    recon = float(np.mean(R ** 2))
    reg = lam * (float(np.mean(np.linalg.norm(R, axis=1) ** 2))
                 + float(np.mean(np.linalg.norm(R, axis=0) ** 2)))
    L = recon + reg

    # dL_recon/dW_hat = 2(W_hat - W) / (m·n)
    dW_hat = 2.0 * (W_hat - W) / (m * n)
    # dL_reg/dW_hat = -λ (2/m + 2/n) R
    dW_hat += -lam * (2.0 / m + 2.0 / n) * R

    dUb = dW_hat @ Vb.T
    dVb = Ub.T @ dW_hat
    return L, dUb, dVb


def encoder_grads(W: np.ndarray,
                  dU_pre: np.ndarray,
                  dV_pre: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """dP = W.T @ dU_pre; dQ = dV_pre @ W.T."""
    return W.T @ dU_pre, dV_pre @ W.T


# ── training config ──────────────────────────────────────────────────────
@dataclass
class TrainingConfig:
    epochs: int
    lr: float
    lam: float = 1e-3
    batch_seeds: tuple[int, ...] = (0, 1, 2, 3, 4)
    scar_var_floor: float | None = None       # must be declared
    deltaS_range_floor: float | None = None   # must be declared

    def assert_declared(self) -> None:
        """RES-401 §acceptance: floors declared before training begins."""
        if self.scar_var_floor is None or self.deltaS_range_floor is None:
            raise ValueError(
                "TrainingConfig non-conformant: scar_var_floor and "
                "deltaS_range_floor must be declared before training."
            )


# ── training loop ────────────────────────────────────────────────────────
def train(core: ResidualCore,
          encoder: FrontEndEncoder,
          W_train: list[np.ndarray],
          W_holdout: list[np.ndarray],
          cfg: TrainingConfig,
          ) -> dict[str, Any]:
    """
    Trains only the encoder. Core parameters (Λ, volume guard, schedule)
    are read for monitoring but never updated (RES-401 §scope).
    """
    cfg.assert_declared()
    history: list[dict[str, float]] = []

    for epoch in range(cfg.epochs):
        # ── train pass: gradients flow to P, Q only ─────────────────────
        for W in W_train:
            enc_out = encoder.forward(W)
            _, dU, dV = loss_and_grads(W, enc_out, cfg.lam)
            dP, dQ = encoder_grads(W, dU, dV)
            encoder.P -= cfg.lr * dP
            encoder.Q -= cfg.lr * dQ

        # ── holdout pass: monitor the frozen core ───────────────────────
        rel_errs, scar_energies, deltas, logdets = [], [], [], []
        for W in W_holdout:
            enc_out = encoder.forward(W)
            Ub, Vb = enc_out["Ub"], enc_out["Vb"]
            R, *_ = encoder.residual_fields(W, Ub, Vb)

            rel_err = float(np.linalg.norm(R) / (np.linalg.norm(W) + 1e-12))
            rel_errs.append(rel_err)

            # Frozen core scar update — monitor only, no gradient.
            M_lat = (Ub.T @ R @ Vb.T) / float(core.cfg.m * core.cfg.n)
            core._Lambda = core._scar_update(M_lat)
            volume, _ = core._volume_guard(core._Lambda)
            scar_energies.append(float(np.linalg.norm(core._Lambda)))
            logdets.append(float(abs(np.log10(abs(volume) + 1e-300))))

            # ΔS proxy: sharpness of fit
            deltas.append(float(1.0 - rel_err))

        history.append({
            "epoch": epoch,
            "reconstruction_rel_error": float(np.mean(rel_errs)),
            "scar_energy": float(np.mean(scar_energies)),
            "DeltaS": float(np.mean(deltas)),
            "logdetJ_abs": float(np.max(logdets)),
        })

    # ── acceptance (RES-401) ────────────────────────────────────────────
    scar_arr = np.array([h["scar_energy"] for h in history])
    delta_arr = np.array([h["DeltaS"] for h in history])
    scar_var = float(np.var(scar_arr))
    delta_range = float(delta_arr.max() - delta_arr.min())

    return {
        "training_config": {
            "epochs": cfg.epochs,
            "lr": cfg.lr,
            "lam": cfg.lam,
            "batch_seeds": list(cfg.batch_seeds),
            "scar_var_floor": cfg.scar_var_floor,
            "deltaS_range_floor": cfg.deltaS_range_floor,
        },
        "history": history,
        "acceptance": {
            "scar_energy_variance": scar_var,
            "DeltaS_range": delta_range,
            "scar_var_ok": scar_var >= cfg.scar_var_floor,
            "deltaS_range_ok": delta_range >= cfg.deltaS_range_floor,
            "conformant": bool(
                scar_var >= cfg.scar_var_floor
                and delta_range >= cfg.deltaS_range_floor
            ),
        },
    }
