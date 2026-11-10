"""Residual studio codec.

``ResidualCore`` factorizes a matrix by repeated bipolar low-rank steps.
Each step projects the residual through a pair of bases, keeps the signs,
fits one least-squares scale, and subtracts. The sum of those steps is
``last_reconstruction``.

The RES-201 control packet stores only layer 0's ``Ub`` and ``Vb``. It
does not store that scale, and it does not store later layers, so the
packet cannot rebuild the approximation. This module keeps the same
factorization and writes a ``studio-codec/1`` packet that can.

Layer-scale mode calls ``ResidualCore._factorize_residual_stack`` so the
factors are the engine's. Component-scale mode is a measured variant: the
same signs, then one scale per rank-1 term, solved jointly. It is not what
the engine does today.

Decode uses only the packet. The bases are an encoder-side dictionary.
"""
from __future__ import annotations

import struct
from typing import Any

import numpy as np

from resileos.core import CoreConfig, ResidualCore

MAGIC = b"RSC1"
VERSION = "studio-codec/1"


def bipolar(values: np.ndarray) -> np.ndarray:
    signed = np.sign(np.asarray(values))
    signed = np.array(signed, dtype=np.float64, copy=True)
    signed[signed == 0] = 1.0
    return signed


def random_bases(m: int, n: int, rank: int, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Fixed ±1 bases. Same draws as ``ResidualCore.__init__`` for this seed."""
    rng = np.random.default_rng(int(seed))
    ub0 = bipolar(rng.standard_normal((m, rank)))
    vb0 = bipolar(rng.standard_normal((rank, n)))
    return ub0, vb0


def _column_row_grams(images: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    batch = np.asarray(images, dtype=np.float64)
    if batch.ndim != 3:
        raise ValueError(f"images must be (N, m, n), got {batch.shape}")
    count, m, n = batch.shape
    if count < 1:
        raise ValueError("need at least one image to fit bases")
    gram_left = np.zeros((m, m), dtype=np.float64)
    gram_right = np.zeros((n, n), dtype=np.float64)
    for matrix in batch:
        gram_left += matrix @ matrix.T
        gram_right += matrix.T @ matrix
    gram_left /= count
    gram_right /= count
    return gram_left, gram_right


def _principal_axes(images: np.ndarray, rank: int) -> tuple[np.ndarray, np.ndarray]:
    """Top ``rank`` eigenvectors of the mean column-space and row-space."""
    gram_left, gram_right = _column_row_grams(images)
    m = gram_left.shape[0]
    n = gram_right.shape[0]
    if rank < 1 or rank > min(m, n):
        raise ValueError(f"rank must be in 1..{min(m, n)}, got {rank}")
    _, left_vecs = np.linalg.eigh(gram_left)
    _, right_vecs = np.linalg.eigh(gram_right)
    # eigh returns ascending eigenvalues. Principal axes come last.
    left = left_vecs[:, ::-1][:, :rank]
    right = right_vecs[:, ::-1][:, :rank]
    return left, right.T


def pca_bipolar_bases(images: np.ndarray, rank: int) -> tuple[np.ndarray, np.ndarray]:
    """±1 pattern of the principal axes. Same type of basis the engine stores."""
    left, right = _principal_axes(images, rank)
    return bipolar(left), bipolar(right)


def pca_real_bases(images: np.ndarray, rank: int) -> tuple[np.ndarray, np.ndarray]:
    """Principal axes kept as real vectors. Codes are still bipolar."""
    return _principal_axes(images, rank)


def logical_bits(m: int, n: int, rank: int, n_layers: int, scale_mode: str) -> int:
    """Information bits, ignoring byte padding and the fixed header.

    Each bipolar factor is one bit. Each scale is one float32 (32 bits).
    Shared bases are a model, not part of the per-image payload.
    """
    if scale_mode not in ("layer", "component"):
        raise ValueError(scale_mode)
    scales = rank if scale_mode == "component" else 1
    return int(n_layers * (m * rank + rank * n + 32 * scales))


def _check_matrix(matrix: np.ndarray) -> np.ndarray:
    array = np.asarray(matrix)
    if array.ndim != 2:
        raise ValueError(f"matrix must be 2-D, got shape {array.shape}")
    return array


def _check_rank(m: int, n: int, rank: int, n_layers: int) -> None:
    if rank < 1 or rank > min(m, n):
        raise ValueError(f"rank must be in 1..{min(m, n)} for a {m}x{n} matrix, got {rank}")
    if n_layers < 1:
        raise ValueError(f"n_layers must be >= 1, got {n_layers}")


def _as_bases(
    m: int,
    n: int,
    rank: int,
    seed: int,
    basis: str,
    bases: tuple[np.ndarray, np.ndarray] | None,
) -> tuple[tuple[np.ndarray, np.ndarray], str]:
    if bases is None:
        if basis != "random":
            raise ValueError(
                "learned bases must be fit on a training set and passed in; "
                "fitting them on the matrix being coded would leak the test image"
            )
        return random_bases(m, n, rank, seed), basis
    ub0 = np.asarray(bases[0], dtype=np.float64)
    vb0 = np.asarray(bases[1], dtype=np.float64)
    if ub0.shape != (m, rank) or vb0.shape != (rank, n):
        raise ValueError(
            f"bases must be ({m}, {rank}) and ({rank}, {n}), got {ub0.shape} and {vb0.shape}"
        )
    return (ub0, vb0), basis


def _engine_layers(
    matrix: np.ndarray,
    ub0: np.ndarray,
    vb0: np.ndarray,
    n_layers: int,
) -> tuple[list[tuple[np.ndarray, np.ndarray, float]], np.ndarray]:
    """Run the engine's residual stack with the given bases.

    ``ResidualCore`` has no public setter for the bases. Replacing
    ``_Ub0`` and ``_Vb0`` before the private stack call is the whole
    difference between a random dictionary and a learned one. The scar
    update is not part of the codec.
    """
    m, n = matrix.shape
    rank = ub0.shape[1]
    core = ResidualCore(
        CoreConfig(m=m, n=n, r=rank, n_residual_layers=n_layers),
        seed=0,
    )
    core._Ub0 = np.array(ub0, dtype=np.float64, copy=True)
    core._Vb0 = np.array(vb0, dtype=np.float64, copy=True)
    core._Ub0[core._Ub0 == 0] = 1.0
    core._Vb0[core._Vb0 == 0] = 1.0
    layers, recon = core._factorize_residual_stack(np.asarray(matrix, dtype=np.float32))
    return layers, np.asarray(recon, dtype=np.float64)


def _component_layers(
    matrix: np.ndarray,
    ub0: np.ndarray,
    vb0: np.ndarray,
    n_layers: int,
) -> list[dict[str, Any]]:
    """Same sign step as the engine, then a joint scale per component.

    Not the engine. ``P = Ub @ Vb`` in the engine has one scale. Here each
    rank-1 term ``outer(Ub[:, k], Vb[k])`` gets its own scale, and the
    scales are the joint least-squares solution on the current residual.
    """
    residual = np.array(matrix, dtype=np.float64, copy=True)
    ub0_f = np.asarray(ub0, dtype=np.float64)
    vb0_f = np.asarray(vb0, dtype=np.float64)
    rank = ub0_f.shape[1]
    layers: list[dict[str, Any]] = []
    for _ in range(n_layers):
        left = bipolar(residual @ vb0_f.T)
        right = bipolar(ub0_f.T @ residual)
        atoms = [np.outer(left[:, k], right[k]) for k in range(rank)]
        gram = np.zeros((rank, rank), dtype=np.float64)
        proj = np.zeros(rank, dtype=np.float64)
        for i in range(rank):
            proj[i] = float(np.sum(residual * atoms[i]))
            for j in range(i, rank):
                gram[i, j] = gram[j, i] = float(np.sum(atoms[i] * atoms[j]))
        gram.flat[:: rank + 1] += 1e-8
        scales = np.linalg.solve(gram, proj)
        hat = np.zeros_like(residual)
        for k in range(rank):
            hat += float(scales[k]) * atoms[k]
        residual = residual - hat
        layers.append(
            {
                "Ub": left.astype(np.float32),
                "Vb": right.astype(np.float32),
                "scale": [float(s) for s in scales],
            }
        )
    return layers


def encode(
    matrix: np.ndarray,
    *,
    rank: int = 4,
    n_layers: int = 4,
    seed: int = 0,
    basis: str = "random",
    bases: tuple[np.ndarray, np.ndarray] | None = None,
    scale_mode: str = "layer",
) -> dict[str, Any]:
    """Factor ``matrix`` and return a packet that decode() can rebuild.

    The packet has no copy of ``matrix`` and no copy of the bases.
    """
    if scale_mode not in ("layer", "component"):
        raise ValueError(f"scale_mode must be 'layer' or 'component', got {scale_mode!r}")
    array = _check_matrix(matrix)
    m, n = int(array.shape[0]), int(array.shape[1])
    rank_i = int(rank)
    layers_i = int(n_layers)
    _check_rank(m, n, rank_i, layers_i)
    (ub0, vb0), basis_name = _as_bases(m, n, rank_i, int(seed), basis, bases)

    if scale_mode == "layer":
        raw, _recon = _engine_layers(array, ub0, vb0, layers_i)
        layers = [
            {
                "Ub": np.asarray(ub, dtype=np.float32),
                "Vb": np.asarray(vb, dtype=np.float32),
                "scale": float(scale),
            }
            for ub, vb, scale in raw
        ]
    else:
        layers = _component_layers(array, ub0, vb0, layers_i)

    return {
        "version": VERSION,
        "shape": [m, n],
        "rank": rank_i,
        "n_layers": layers_i,
        "scale_mode": scale_mode,
        "basis": basis_name,
        "layers": layers,
        "logical_bits": logical_bits(m, n, rank_i, layers_i, scale_mode),
    }


def decode(packet: dict[str, Any]) -> np.ndarray:
    """Rebuild the approximation from per-layer factors and scales only."""
    m, n = int(packet["shape"][0]), int(packet["shape"][1])
    mode = packet["scale_mode"]
    if mode not in ("layer", "component"):
        raise ValueError(f"unknown scale_mode {mode!r}")
    acc = np.zeros((m, n), dtype=np.float64)
    for layer in packet["layers"]:
        ub = np.asarray(layer["Ub"], dtype=np.float64)
        vb = np.asarray(layer["Vb"], dtype=np.float64)
        if ub.shape[0] != m or vb.shape[1] != n or ub.shape[1] != vb.shape[0]:
            raise ValueError(f"layer factor shape {ub.shape}, {vb.shape} does not match {(m, n)}")
        if mode == "layer":
            acc += float(layer["scale"]) * (ub @ vb)
        else:
            scales = np.asarray(layer["scale"], dtype=np.float64).reshape(-1)
            if scales.shape[0] != ub.shape[1]:
                raise ValueError(
                    f"component scales {scales.shape[0]} do not match rank {ub.shape[1]}"
                )
            for k, scale in enumerate(scales):
                acc += float(scale) * np.outer(ub[:, k], vb[k])
    return acc


def pack_packet(packet: dict[str, Any]) -> bytes:
    """Pack ±1 factors as bits and scales as float32, plus a 14-byte header."""
    m, n = int(packet["shape"][0]), int(packet["shape"][1])
    rank = int(packet["rank"])
    n_layers = int(packet["n_layers"])
    mode = 1 if packet["scale_mode"] == "component" else 0
    if packet["scale_mode"] not in ("layer", "component"):
        raise ValueError(packet["scale_mode"])
    header = MAGIC + struct.pack("<5H", m, n, rank, n_layers, mode)
    body = bytearray()
    for layer in packet["layers"]:
        ub = np.asarray(layer["Ub"])
        vb = np.asarray(layer["Vb"])
        if ub.shape != (m, rank) or vb.shape != (rank, n):
            raise ValueError(f"expected Ub {(m, rank)} and Vb {(rank, n)}, got {ub.shape}, {vb.shape}")
        if np.any(np.abs(np.abs(ub) - 1.0) > 1e-5) or np.any(np.abs(np.abs(vb) - 1.0) > 1e-5):
            raise ValueError("factors must be ±1 to pack as bits")
        body += np.packbits(ub.ravel() > 0).tobytes()
        body += np.packbits(vb.ravel() > 0).tobytes()
        if mode == 0:
            scales = np.array([float(layer["scale"])], dtype=np.float32)
        else:
            scales = np.asarray(layer["scale"], dtype=np.float32).reshape(rank)
        body += scales.tobytes()
    return header + bytes(body)


def unpack_packet(buf: bytes) -> dict[str, Any]:
    """Inverse of ``pack_packet``. Scales come back as float32 values."""
    if len(buf) < 14 or buf[:4] != MAGIC:
        raise ValueError("not a studio-codec/1 payload")
    m, n, rank, n_layers, mode = struct.unpack_from("<5H", buf, 4)
    offset = 14
    ub_count = int(m) * int(rank)
    vb_count = int(rank) * int(n)
    ub_nbytes = (ub_count + 7) // 8
    vb_nbytes = (vb_count + 7) // 8
    scale_count = int(rank) if mode else 1
    layers: list[dict[str, Any]] = []
    for _ in range(int(n_layers)):
        ub_raw = np.unpackbits(np.frombuffer(buf, dtype=np.uint8, offset=offset, count=ub_nbytes))
        offset += ub_nbytes
        vb_raw = np.unpackbits(np.frombuffer(buf, dtype=np.uint8, offset=offset, count=vb_nbytes))
        offset += vb_nbytes
        scale_bytes = buf[offset : offset + 4 * scale_count]
        scales = np.array(struct.unpack("<" + "f" * scale_count, scale_bytes), dtype=np.float64)
        offset += 4 * scale_count
        ub = (ub_raw[:ub_count].astype(np.float32) * 2.0 - 1.0).reshape(m, rank)
        vb = (vb_raw[:vb_count].astype(np.float32) * 2.0 - 1.0).reshape(rank, n)
        scale: Any
        if mode == 0:
            scale = float(scales[0])
        else:
            scale = [float(s) for s in scales]
        layers.append({"Ub": ub, "Vb": vb, "scale": scale})
    if offset != len(buf):
        raise ValueError(f"payload length {len(buf)} does not match the header (read {offset})")
    scale_mode = "component" if mode else "layer"
    return {
        "version": VERSION,
        "shape": [int(m), int(n)],
        "rank": int(rank),
        "n_layers": int(n_layers),
        "scale_mode": scale_mode,
        "basis": "packed",
        "layers": layers,
        "logical_bits": logical_bits(int(m), int(n), int(rank), int(n_layers), scale_mode),
    }


def res201_layer0_product(
    matrix: np.ndarray,
    *,
    rank: int = 4,
    n_layers: int = 4,
    seed: int = 0,
) -> dict[str, Any]:
    """What the RES-201 packet alone can rebuild, and what the engine summed.

    ``step`` puts layer 0's ``Ub`` and ``Vb`` on the packet. The naive
    product ``Ub @ Vb`` drops the least-squares scale and every later layer.
    """
    array = np.asarray(_check_matrix(matrix), dtype=np.float32)
    m, n = int(array.shape[0]), int(array.shape[1])
    _check_rank(m, n, int(rank), int(n_layers))
    core = ResidualCore(
        CoreConfig(m=m, n=n, r=int(rank), n_residual_layers=int(n_layers)),
        seed=int(seed),
    )
    packet = core.step(array)
    if core.last_reconstruction is None or core.last_packet is None:
        raise RuntimeError("core produced no reconstruction")
    naive = np.asarray(packet.Ub, dtype=np.float64) @ np.asarray(packet.Vb, dtype=np.float64)
    recon = np.asarray(core.last_reconstruction, dtype=np.float64)
    return {
        "naive": naive,
        "engine_reconstruction": recon,
        "stored_scale": False,
        "layers_in_packet": 1,
        "n_layers_computed": int(n_layers),
    }
