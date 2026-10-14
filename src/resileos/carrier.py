"""
Substrate carrier: a trainable interface between the frozen substrate
and a downstream model.

The substrate produces a control packet (RES-201) plus optional
monitors (CSI, order parameter, Titanos stats, direction head outputs,
agency state). All of these are NumPy arrays or scalars, produced by
frozen code.

The carrier packs them into a fixed-size feature vector, runs a small
trainable torch MLP, and returns a modulation tensor of caller-declared
shape.

Gradient flow:

    downstream loss
      -> carrier MLP parameters (trainable)
      -> feature pack (NumPy, no autograd)
      -> substrate internals (frozen)

The substrate is never part of the autograd graph. The carrier is the
only trainable component. This preserves RES-200, RES-201, RES-401.
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

import numpy as np
import torch
import torch.nn as nn


def packet_feature_dim(m: int, n: int, r: int) -> int:
    """
    Fixed dimension of the packet feature vector for a given shape.

    Layout:
        Ub.ravel()              m * r
        Vb.ravel()              r * n
        Lambda.ravel()          r * r
        mean(row_s_k)           1
        mean(col_s_k)           1
        mean(lat_s_k)           1
        mu                      1
        DeltaS                  1
        F_res                   1
        log10(|volume|)         1
        volume_ok               1
        rank                    1
    """
    return m * r + r * n + r * r + 9


def pack_packet(packet: Any, m: int, n: int, r: int) -> np.ndarray:
    """
    Extract a fixed-size float64 feature vector from a packet.

    Accepts a dict or an object exposing the RES-201 attributes. Does
    not modify the packet.
    """
    get = (lambda k: packet[k]) if isinstance(packet, dict) \
          else (lambda k: getattr(packet, k))

    Ub = np.asarray(get("Ub"), dtype=np.float64).ravel()
    Vb = np.asarray(get("Vb"), dtype=np.float64).ravel()
    Lam = np.asarray(get("Lambda"), dtype=np.float64).ravel()

    if Ub.size != m * r or Vb.size != r * n or Lam.size != r * r:
        raise ValueError(
            f"packet shape mismatch: Ub {Ub.size} (want {m*r}), "
            f"Vb {Vb.size} (want {r*n}), Lambda {Lam.size} (want {r*r})"
        )

    row_s = np.asarray(get("row_s_k"), dtype=np.float64)
    col_s = np.asarray(get("col_s_k"), dtype=np.float64)
    lat_s = np.asarray(get("lat_s_k"), dtype=np.float64)

    scalars = np.array([
        float(np.mean(row_s)) if row_s.size else 0.0,
        float(np.mean(col_s)) if col_s.size else 0.0,
        float(np.mean(lat_s)) if lat_s.size else 0.0,
        float(get("mu")),
        float(get("DeltaS")),
        float(get("F_res")),
        float(np.log10(abs(float(get("volume"))) + 1e-300)),
        1.0 if bool(get("volume_ok")) else 0.0,
        float(get("rank")),
    ], dtype=np.float64)

    return np.concatenate([Ub, Vb, Lam, scalars])


class SubstrateCarrier(nn.Module):
    """
    Trainable interface. Consumes frozen substrate features and emits
    a modulation tensor of caller-declared shape.

    Parameters
    ----------
    m, n, r : int
        Packet shape. Sets the packet feature dimension.
    output_shape : sequence of int
        Shape of the modulation tensor. E.g. (k, d_model) for prefix
        embeddings, (n_layers,) for per-layer gates, (d_model,) for a
        bias vector.
    hidden_dim : int
        MLP hidden width.
    n_layers : int
        MLP depth. 1 = single linear.
    extra_dim : int
        Dimension of optional caller-supplied features concatenated
        after the packet features. Default 0.
    seed : int
        Torch seed for reproducible init.
    zero_init_output : bool
        If True (default), the final linear layer is zero-initialized so
        that the carrier starts as an identity modulation (no effect on
        the base model at step 0). This makes the "carrier off" and
        "carrier on at init" baselines match.
    """

    def __init__(
        self,
        m: int,
        n: int,
        r: int,
        output_shape: Sequence[int],
        hidden_dim: int = 128,
        n_layers: int = 2,
        extra_dim: int = 0,
        seed: int = 0,
        zero_init_output: bool = True,
    ) -> None:
        super().__init__()
        self.m, self.n, self.r = int(m), int(n), int(r)
        self.packet_dim = packet_feature_dim(m, n, r)
        self.extra_dim = int(extra_dim)
        self.feature_dim = self.packet_dim + self.extra_dim
        self.output_shape = tuple(int(x) for x in output_shape)
        self.out_dim = int(np.prod(self.output_shape))

        torch.manual_seed(int(seed))

        layers: list[nn.Module] = []
        in_dim = self.feature_dim
        for _ in range(max(0, n_layers - 1)):
            layers.append(nn.Linear(in_dim, hidden_dim))
            layers.append(nn.GELU())
            in_dim = hidden_dim
        layers.append(nn.Linear(in_dim, self.out_dim))
        self.mlp = nn.Sequential(*layers)

        if zero_init_output:
            last = self.mlp[-1]
            if isinstance(last, nn.Linear):
                nn.init.zeros_(last.weight)
                nn.init.zeros_(last.bias)

    # ── feature extraction (NumPy, no autograd) ──────────────────────
    def feature_vector(self, packet: Any,
                       extra: Optional[np.ndarray] = None) -> np.ndarray:
        feats = [pack_packet(packet, self.m, self.n, self.r)]
        if self.extra_dim > 0:
            if extra is None:
                raise ValueError("extra_dim > 0 but extra is None")
            e = np.asarray(extra, dtype=np.float64).ravel()
            if e.size != self.extra_dim:
                raise ValueError(
                    f"extra feature size {e.size} != extra_dim {self.extra_dim}"
                )
            feats.append(e)
        return np.concatenate(feats)

    # ── forward (gradients flow through the MLP only) ────────────────
    def forward(self, packet: Any,
                extra: Optional[np.ndarray] = None) -> torch.Tensor:
        f = self.feature_vector(packet, extra)
        x = torch.from_numpy(f).to(dtype=torch.float32)
        out = self.mlp(x)
        return out.view(self.output_shape)


__all__ = ["SubstrateCarrier", "pack_packet", "packet_feature_dim"]
