#!/usr/bin/env python3
"""
Toy carrier evolution A/B.

Base model: y = A @ x  (A frozen, random).
Target:     y* = A @ x + c, where c is sampled per example.
Carrier:    sees a noisy observation of c, produces a bias b.
            Trained so that y + b approximates y*.

Base loss without carrier:  E ||c||^2         (predict nothing).
Carrier loss after training: E ||b - c||^2    (denoised correction).

The point: the carrier's job is to extract what it can from the
features. The substrate's job is to supply them. If the carrier
reduces loss, the substrate's feature bus carries usable information
into a trainable interface.

Real packets from ResidualCore. Synthetic correction target and noisy
observation. No frozen contract touched.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from resileos.core import CoreConfig, ResidualCore
from resileos.carrier import SubstrateCarrier


def main() -> int:
    torch.manual_seed(0)
    rng = np.random.default_rng(0)

    m, n, r = 8, 8, 4
    d_out = 16
    hidden = 128
    n_train = 512
    n_val = 128
    batch = 64
    steps = 400
    lr = 1e-3
    sigma = 0.5

    # Frozen base model: y = A @ x, A random fixed.
    A = rng.standard_normal((d_out, d_out))

    # Real packets from the residual core.
    core = ResidualCore(CoreConfig(m=m, n=n, r=r), seed=0)

    def make_sample(idx: int):
        W = rng.standard_normal((m, n))
        packet = core.step(W, mu=int(idx % 2), F_res=0.1, DeltaS=0.5)
        c = rng.standard_normal(d_out)
        obs = c + sigma * rng.standard_normal(d_out)
        return packet, obs.astype(np.float64), c.astype(np.float64)

    train = [make_sample(i) for i in range(n_train)]
    val = [make_sample(i) for i in range(n_val)]

    carrier = SubstrateCarrier(
        m=m, n=n, r=r,
        output_shape=(d_out,),
        hidden_dim=hidden,
        n_layers=2,
        extra_dim=d_out,
        seed=0,
    )

    optimizer = torch.optim.Adam(carrier.parameters(), lr=lr)

    # ── baseline: predict zero correction ────────────────────────────
    base_losses = [float(np.mean(c**2)) for _, _, c in val]
    base_mse = float(np.mean(base_losses))

    # ── train carrier only ───────────────────────────────────────────
    step = 0
    while step < steps:
        for i in range(0, n_train, batch):
            optimizer.zero_grad()
            batch_samples = train[i:i + batch]
            total = torch.zeros(())
            for packet, obs, c in batch_samples:
                b = carrier(packet, extra=obs)
                total = total + ((b - torch.from_numpy(c).float()) ** 2).mean()
            (total / len(batch_samples)).backward()
            optimizer.step()
            step += 1
            if step >= steps:
                break

    # ── evaluate ─────────────────────────────────────────────────────
    with torch.no_grad():
        carrier_losses = []
        for packet, obs, c in val:
            b = carrier(packet, extra=obs)
            carrier_losses.append(
                float(((b - torch.from_numpy(c).float()) ** 2).mean())
            )
        carrier_mse = float(np.mean(carrier_losses))

    reduction = 100.0 * (base_mse - carrier_mse) / (base_mse + 1e-12)

    print("=== Toy carrier evolution A/B ===")
    print(f"base MSE (predict zero):  {base_mse:.4f}")
    print(f"carrier MSE (trained):    {carrier_mse:.4f}")
    print(f"reduction:                {reduction:+.2f}%")
    print()
    print("grads populated:",
          all(p.grad is not None for p in carrier.parameters()))
    print("n_train:", n_train, " n_val:", n_val, " steps:", steps)

    # Sanity: the theoretical optimum for a linear denoiser under
    # Gaussian noise is E[c|obs] = (1/(1+sigma^2)) obs.
    theoretical = float(np.mean(
        ((1.0 / (1.0 + sigma * sigma) - 1.0) ** 2) * np.ones(d_out)
        + (sigma * sigma) * (1.0 / (1.0 + sigma * sigma)) ** 2 * np.ones(d_out)
    ))
    print(f"theoretical min per-elt:  {theoretical:.4f}  "
          f"(closed form, not asserted)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
