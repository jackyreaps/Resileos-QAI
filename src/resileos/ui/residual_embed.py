"""Residual embedding scaffold.

Projects a frame or short sequence into a residual coordinate
that the store can gate. This is scaffolding for later hardware
or software encoding. It does not claim to implement the full
cascade or the oscillating engine.

The coordinate is a stable address:
  belt, frame, residual_bin, debt

Later encoders replace the feature function. The address shape stays.

An optional ``scale`` names a belt-scale control (see
``resileos.ui.belt_scale``). That control sets the cascade address
(belt index and frame) via ``cascade_address``. It does not rebuild
the pixel matrix, call learn, or write a scar.

``suite_residual`` still receives the original ``belt`` argument, not
the scale index. The scale index would change ``residual_bin``
(the placeholder label includes ``belt % 4``), and the orientation
index is only meant to change the address. Pixel features and
``residual_bin`` therefore stay the same as a no-scale call that
used the same ``belt``. With ``scale`` omitted or empty, the returned
dict is unchanged from the previous signature.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from resileos.ui.cascade_address import cascade_address
from resileos.ui.suite_residual import suite_residual


def residual_bin(mean_luma: float, edge_density: float) -> str:
    """Coarse residual bin from two scalars. Placeholder for the suite residual."""
    if edge_density > 0.2 and mean_luma > 0.5:
        return "high_high"
    if edge_density > 0.2:
        return "high_low"
    if mean_luma > 0.5:
        return "low_high"
    return "low_low"


def embed_frame(
    arr: np.ndarray,
    *,
    belt: int = 0,
    frame: int = 0,
    scale: str | None = None,
) -> dict[str, Any]:
    """Embed one frame into a residual address.

    arr: HxW or HxWxC
    scale: optional belt scale name. When set, the cascade address
    uses that control's belt index and frame. The original ``belt``
    is still passed to ``suite_residual``.
    """
    bin_belt = int(belt)
    address_belt = bin_belt
    address_frame = int(frame)
    control = None
    if scale:
        from resileos.ui.belt_scale import matrix_control

        control = matrix_control(scale)
        address_belt = int(control["belt"])
        address_frame = int(control["frame"])
    if arr.ndim == 3:
        gray = arr[..., :3].astype(np.float32)
        if gray.max() > 1.5:
            gray = gray / 255.0
        gray = 0.2126 * gray[..., 0] + 0.7152 * gray[..., 1] + 0.0722 * gray[..., 2]
    else:
        gray = arr.astype(np.float32)
        if gray.max() > 1.5:
            gray = gray / 255.0
    gy, gx = np.gradient(gray)
    edge = float((np.hypot(gx, gy) > 0.08).mean())
    luma = float(gray.mean())
    rbin = suite_residual(luma, edge, bin_belt)
    out: dict[str, Any] = {
        "belt": address_belt,
        "frame": address_frame,
        "residual_bin": rbin,
        "mean_luma": round(luma, 4),
        "edge_density": round(edge, 4),
        "debt": 1.0,
        "note": "Scaffold address. Replace residual_bin with suite residual when coded.",
    }
    if control is not None:
        path = cascade_address(address_belt, address_frame, rbin)
        out["scale"] = control["scale"]
        out["orientation"] = control["orientation"]
        out["proportion"] = control["proportion"]
        out["phi_weight"] = control["phi_weight"]
        out["path"] = path["path"]
        out["residual"] = path["residual"]
    return out


def address_triple(embed: dict[str, Any], subject: str = "frame") -> dict[str, str]:
    """Triple the gate can accept or reject."""
    obj = f"belt{embed['belt']}_frame{embed['frame']}_{embed['residual_bin']}"
    return {"subject": subject, "relation": "residual_address", "obj": obj}
