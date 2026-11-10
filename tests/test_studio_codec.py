"""The studio packet stores every layer scale and decode rebuilds from it."""
from __future__ import annotations

import numpy as np
import pytest

from resileos.core import CoreConfig, ResidualCore
from studio.codec import (
    decode,
    encode,
    logical_bits,
    pack_packet,
    pca_bipolar_bases,
    pca_real_bases,
    res201_layer0_product,
    unpack_packet,
)


def _matrix(seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.random((8, 8))


def test_packet_stores_a_scale_per_layer_and_decode_matches_the_engine():
    matrix = _matrix(0)
    packet = encode(matrix, rank=4, n_layers=4, seed=1, scale_mode="layer")
    assert packet["version"] == "studio-codec/1"
    assert len(packet["layers"]) == 4
    assert [type(layer["scale"]) for layer in packet["layers"]] == [float, float, float, float]
    assert "reconstruction" not in packet

    core = ResidualCore(CoreConfig(m=8, n=8, r=4, n_residual_layers=4), seed=1)
    core.step(np.asarray(matrix, dtype=np.float32))
    rebuilt = decode(packet)
    mse = float(np.mean((rebuilt - core.last_reconstruction) ** 2))
    assert mse < 1e-8


def test_packed_payload_round_trips_without_the_original():
    matrix = _matrix(2)
    packet = encode(matrix, rank=3, n_layers=5, seed=0)
    blob = pack_packet(packet)
    assert blob[:4] == b"RSC1"
    restored = unpack_packet(blob)
    assert restored["basis"] == "packed"
    assert all(isinstance(layer["scale"], float) for layer in restored["layers"])
    mse = float(np.mean((decode(restored) - decode(packet)) ** 2))
    # Scales travel as float32. The in-memory packet keeps the engine's float.
    assert mse < 1e-10
    assert len(blob) > packet["logical_bits"] // 8


def test_dropping_the_scale_is_not_the_same_reconstruction():
    matrix = _matrix(3)
    packet = encode(matrix, rank=4, n_layers=3, seed=4)
    stripped = {
        **packet,
        "layers": [{**layer, "scale": 1.0} for layer in packet["layers"]],
    }
    faithful = float(np.mean((decode(packet) - matrix) ** 2))
    dropped = float(np.mean((decode(stripped) - matrix) ** 2))
    assert dropped > faithful + 1e-3


def test_res201_packet_product_is_not_the_engine_reconstruction():
    matrix = _matrix(4)
    gap = res201_layer0_product(matrix, rank=4, n_layers=4, seed=0)
    assert gap["stored_scale"] is False
    assert gap["layers_in_packet"] == 1
    naive_mse = float(np.mean((gap["naive"] - gap["engine_reconstruction"]) ** 2))
    studio = encode(matrix, rank=4, n_layers=4, seed=0)
    studio_mse = float(np.mean((decode(studio) - gap["engine_reconstruction"]) ** 2))
    assert studio_mse < 1e-8
    assert naive_mse > studio_mse + 1e-3


def test_decode_does_not_need_the_bases():
    images = np.random.default_rng(5).random((12, 6, 6))
    bases = pca_bipolar_bases(images, rank=2)
    packet = encode(
        images[0],
        rank=2,
        n_layers=2,
        basis="pca_bipolar",
        bases=bases,
    )
    assert packet["basis"] == "pca_bipolar"
    rebuilt = decode(unpack_packet(pack_packet(packet)))
    assert rebuilt.shape == (6, 6)
    assert np.isfinite(rebuilt).all()


def test_pca_real_bases_still_go_through_the_engine_stack():
    images = np.random.default_rng(6).normal(size=(10, 8, 8))
    bases = pca_real_bases(images, rank=3)
    packet = encode(images[1], rank=3, n_layers=2, basis="pca_real", bases=bases, scale_mode="layer")
    core = ResidualCore(CoreConfig(m=8, n=8, r=3, n_residual_layers=2), seed=0)
    core._Ub0 = np.array(bases[0], copy=True)
    core._Vb0 = np.array(bases[1], copy=True)
    core._Ub0[core._Ub0 == 0] = 1.0
    core._Vb0[core._Vb0 == 0] = 1.0
    _layers, recon = core._factorize_residual_stack(np.asarray(images[1], dtype=np.float32))
    mse = float(np.mean((decode(packet) - recon) ** 2))
    assert mse < 1e-8


def test_component_mode_stores_one_scale_per_component():
    matrix = _matrix(7)
    packet = encode(matrix, rank=4, n_layers=2, seed=1, scale_mode="component")
    assert packet["scale_mode"] == "component"
    assert [len(layer["scale"]) for layer in packet["layers"]] == [4, 4]
    restored = unpack_packet(pack_packet(packet))
    mse = float(np.mean((decode(restored) - decode(packet)) ** 2))
    assert mse < 1e-8
    assert packet["logical_bits"] == logical_bits(8, 8, 4, 2, "component")
    assert packet["logical_bits"] > logical_bits(8, 8, 4, 2, "layer")


def test_rejects_a_vector_and_an_oversized_rank():
    with pytest.raises(ValueError):
        encode(np.zeros(8), rank=1, n_layers=1)
    with pytest.raises(ValueError):
        encode(np.zeros((4, 4)), rank=5, n_layers=1)
    with pytest.raises(ValueError):
        encode(np.zeros((4, 4)), rank=2, n_layers=1, basis="pca_bipolar")


def test_learned_bases_are_not_fit_on_the_coded_matrix_alone():
    images = np.stack([_matrix(i) for i in range(8)])
    bases = pca_bipolar_bases(images[:6], rank=2)
    held_out = encode(images[7], rank=2, n_layers=2, basis="pca_bipolar", bases=bases)
    assert held_out["shape"] == [8, 8]
    assert decode(held_out).shape == (8, 8)
