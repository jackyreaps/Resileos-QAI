"""Pluggable residual codecs.

The shipped pair is the PCA-basis encoder from the digits study, with one
scale per component. ``decode`` is the linear sum of those scaled factors.
A learned conv encoder/decoder can replace this class later. It is
registered and unavailable. Nothing here calls ``learn`` or ``ResidualCore.step``.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Protocol

import numpy as np

_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
if _SCRIPTS.is_dir() and str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from studio.codec import (  # noqa: E402
    decode,
    encode,
    logical_bits,
    pack_packet,
    pca_real_bases,
)


class CodecUnavailable(RuntimeError):
    """The named codec is a drop-in point, not a trained model."""


class ResidualCodec(Protocol):
    """Encoder and decoder outside the core. The packet is the only contract."""

    name: str
    available: bool

    def encode_matrix(self, matrix: np.ndarray) -> dict[str, Any]:
        """Return a studio-codec/1 packet. Do not update the scar matrix."""

    def decode(self, packet: dict[str, Any]) -> np.ndarray:
        """Rebuild an image from the packet alone."""


def project_gray(image: np.ndarray, m: int = 8, n: int = 8) -> np.ndarray:
    """8×8 grayscale in about [0, 1]. Same resize idea as the frame codec.

    PSNR for this mode is on this projection, not on the original file.
    """
    array = np.asarray(image)
    if array.ndim == 3:
        rgb = array[..., :3].astype(np.float64)
        if rgb.size and float(rgb.max()) > 1.5:
            rgb = rgb / 255.0
        gray = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    elif array.ndim == 2:
        gray = array.astype(np.float64)
        if gray.size and float(gray.max()) > 1.5:
            gray = gray / 255.0
    else:
        raise ValueError(f"image must be 2-D or 3-D, got {array.shape}")
    if gray.size == 0:
        gray = np.zeros((1, 1), dtype=np.float64)
    height, width = gray.shape
    ys = np.clip(np.round(np.linspace(0, height - 1, m)).astype(int), 0, height - 1)
    xs = np.clip(np.round(np.linspace(0, width - 1, n)).astype(int), 0, width - 1)
    return gray[ys][:, xs].astype(np.float64)


class PcaComponentCodec:
    """PCA real bases, per-component scales, rank 4, 4 layers.

    Bases are fit on the sklearn digits train split (seed 0, 36 test images
    per class). That is the encoder from the digits study. The decoder is
    the linear sum. Neither one is inside ResidualCore.step.
    """

    name = "pca_component"
    available = True
    rank = 4
    n_layers = 4
    scale_mode = "component"

    def __init__(self) -> None:
        self._bases: tuple[np.ndarray, np.ndarray] | None = None
        self.images: np.ndarray | None = None
        self.labels: np.ndarray | None = None
        self.train_idx: np.ndarray | None = None
        self.test_idx: np.ndarray | None = None

    def fit_digits(self) -> None:
        from sklearn.datasets import load_digits

        bunch = load_digits()
        images = bunch.images.astype(np.float64) / 16.0
        labels = bunch.target.astype(int)
        train_idx: list[int] = []
        test_idx: list[int] = []
        rng = np.random.default_rng(0)
        for label in range(10):
            pool = np.flatnonzero(labels == label)
            order = rng.permutation(pool)
            test_idx.extend(int(i) for i in order[:36])
            train_idx.extend(int(i) for i in order[36:])
        self.images = images
        self.labels = labels
        self.train_idx = np.array(train_idx, dtype=int)
        self.test_idx = np.array(test_idx, dtype=int)
        self._bases = pca_real_bases(images[self.train_idx], self.rank)

    def ensure(self) -> None:
        if self._bases is None:
            self.fit_digits()

    def holdout_matrix(self, label: int) -> np.ndarray:
        self.ensure()
        assert self.images is not None and self.labels is not None and self.test_idx is not None
        label_i = int(label)
        chosen = [int(i) for i in self.test_idx if int(self.labels[i]) == label_i]
        if not chosen:
            raise ValueError(f"no holdout digit for class {label_i}")
        return np.array(self.images[chosen[0]], dtype=np.float64, copy=True)

    def project(self, image: np.ndarray) -> np.ndarray:
        return project_gray(image, 8, 8)

    def encode_matrix(self, matrix: np.ndarray) -> dict[str, Any]:
        self.ensure()
        assert self._bases is not None
        packet = encode(
            matrix,
            rank=self.rank,
            n_layers=self.n_layers,
            basis="pca_real",
            bases=self._bases,
            scale_mode=self.scale_mode,
        )
        if packet["scale_mode"] != "component":
            raise RuntimeError("pca codec must store per-component scales")
        return packet

    def decode(self, packet: dict[str, Any]) -> np.ndarray:
        return decode(packet)


class LearnedConvCodec:
    """Drop-in point for a trained conv encoder and decoder. Not trained."""

    name = "learned_conv"
    available = False

    def encode_matrix(self, matrix: np.ndarray) -> dict[str, Any]:
        del matrix
        raise CodecUnavailable(
            "No conv encoder is trained. A later model implements "
            "encode_matrix and decode and is selected by name."
        )

    def decode(self, packet: dict[str, Any]) -> np.ndarray:
        del packet
        raise CodecUnavailable(
            "No conv decoder is trained. The linear sum remains the decoder."
        )


_CODECS: dict[str, type] = {
    PcaComponentCodec.name: PcaComponentCodec,
    LearnedConvCodec.name: LearnedConvCodec,
}
_PCA: PcaComponentCodec | None = None


def codec_names() -> list[str]:
    return list(_CODECS)


def open_codec(name: str = "pca_component") -> ResidualCodec:
    if name not in _CODECS:
        raise KeyError(f"unknown codec {name!r}; known: {codec_names()}")
    if name == PcaComponentCodec.name:
        global _PCA
        if _PCA is None:
            _PCA = PcaComponentCodec()
        return _PCA
    return _CODECS[name]()


def packet_summary(packet: dict[str, Any]) -> dict[str, Any]:
    """JSON-sized description. Factors stay out of the UI payload."""
    blob = pack_packet(packet)
    scales = []
    for layer in packet["layers"]:
        scale = layer["scale"]
        if isinstance(scale, (int, float)):
            scales.append(1)
        else:
            scales.append(int(np.asarray(scale).size))
    return {
        "version": packet["version"],
        "shape": list(packet["shape"]),
        "rank": int(packet["rank"]),
        "n_layers": int(packet["n_layers"]),
        "scale_mode": packet["scale_mode"],
        "basis": packet.get("basis"),
        "logical_bits": int(
            packet.get("logical_bits")
            or logical_bits(
                int(packet["shape"][0]),
                int(packet["shape"][1]),
                int(packet["rank"]),
                int(packet["n_layers"]),
                str(packet["scale_mode"]),
            )
        ),
        "packed_bytes": len(blob),
        "scales_per_layer": scales,
    }
