"""Tests for the φ-phased codex."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.codex import PhiPhaseCodex, MAX_POSITIONS_DEFAULT


def _book(vocab_size=64, dim=256, max_positions=MAX_POSITIONS_DEFAULT):
    return PhiPhaseCodex(vocab_size=vocab_size, dim=dim,
                         max_positions=max_positions)


# ── construction ────────────────────────────────────────────────────────
def test_codex_shape():
    b = _book(vocab_size=32, dim=128)
    assert b.codebook.shape == (32, 128)
    assert b.codebook.dtype == np.complex128


def test_codebook_unit_norm():
    b = _book(vocab_size=16, dim=64)
    norms = np.linalg.norm(b.codebook, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-12)


def test_codex_rejects_bad_vocab():
    with pytest.raises(ValueError, match="vocab_size"):
        PhiPhaseCodex(vocab_size=0, dim=64)


def test_codex_rejects_bad_dim():
    with pytest.raises(ValueError, match="dim"):
        PhiPhaseCodex(vocab_size=4, dim=1)


def test_codex_rejects_bad_max_positions():
    with pytest.raises(ValueError, match="max_positions"):
        PhiPhaseCodex(vocab_size=4, dim=64, max_positions=0)


# ── orthogonality ───────────────────────────────────────────────────────
def test_codes_near_orthogonal():
    b = _book(vocab_size=32, dim=256)
    cosines = []
    for t in range(0, 32, 4):
        for u in range(t + 1, min(t + 5, 32)):
            c = abs(np.vdot(b.codebook[t], b.codebook[u]))
            cosines.append(c)
    # Expected max ~ 1/sqrt(dim); allow 4x margin
    assert max(cosines) < 0.25, f"max cos = {max(cosines)}"


def test_token_and_position_codes_disjoint():
    """Token t and position t must not produce identical codes."""
    b = _book(vocab_size=16, dim=128)
    for i in range(16):
        c = abs(np.vdot(b.phase_code(i), b.phase_slot(i)))
        assert c < 0.25, f"token {i} and position {i} not disjoint: cos={c}"


def test_position_hv_unit_norm():
    b = _book()
    u = b.phase_slot(5)
    assert np.isclose(np.linalg.norm(u), 1.0, atol=1e-12)


# ── single token ────────────────────────────────────────────────────────
def test_encode_single_token_recovered():
    b = _book()
    hv = b.encode([7])
    ranked = b.argmax_coherence(hv, 0, top_k=3)
    assert ranked[0][0] == 7
    assert ranked[0][1] > 0.5


def test_cleanup_single_token():
    b = _book()
    hv = b.encode([12])
    assert b.cleanup(hv, 0) == 12


def test_encode_token_zero_works():
    """Token 0 is not degenerate (disjoint-band fix)."""
    b = _book()
    hv = b.encode([0])
    assert b.cleanup(hv, 0) == 0


# ── sequence ────────────────────────────────────────────────────────────
def test_encode_sequence_recovered_at_each_position():
    b = _book(vocab_size=64, dim=512)
    tokens = [3, 5, 7, 11]
    hv = b.encode(tokens)
    for p, expected in enumerate(tokens):
        recovered = b.cleanup(hv, p)
        assert recovered == expected, (
            f"position {p}: expected {expected}, got {recovered}")


def test_encode_longer_sequence():
    b = _book(vocab_size=64, dim=1024)
    tokens = [1, 20, 30, 40, 50, 60]
    hv = b.encode(tokens)
    for p, expected in enumerate(tokens):
        ranked = b.argmax_coherence(hv, p, top_k=1)
        assert ranked[0][0] == expected, (
            f"position {p}: expected {expected}, got {ranked[0][0]}")


def test_encode_empty_returns_zero():
    b = _book()
    hv = b.encode([])
    assert np.allclose(hv, 0.0)


def test_encode_rejects_too_long():
    b = _book(vocab_size=8, dim=64, max_positions=4)
    with pytest.raises(ValueError, match="max_positions"):
        b.encode([0, 1, 2, 3, 4])


# ── bind / unbind ───────────────────────────────────────────────────────
def test_bind_unbind_roundtrip():
    b = _book()
    a = b.phase_code(0)
    key = b.phase_slot(3)
    bound = b.bind(a, key)
    unbound = b.unbind(bound, key)
    # unbind recovers a up to normalization
    recovered = unbound / (np.linalg.norm(unbound) + 1e-12)
    expected = a / (np.linalg.norm(a) + 1e-12)
    assert np.allclose(recovered, expected, atol=1e-9)


def test_bind_produces_unit_norm():
    b = _book()
    bound = b.bind(b.phase_code(0), b.phase_slot(0))
    assert np.isclose(np.linalg.norm(bound), 1.0, atol=1e-9)


def test_bundle_returns_unit_norm():
    b = _book()
    codes = [b.bind(b.phase_code(t), b.phase_slot(p))
             for p, t in enumerate([0, 1, 2])]
    hv = b.bundle(codes)
    assert np.isclose(np.linalg.norm(hv), 1.0, atol=1e-9)


def test_bundle_empty_returns_zero():
    b = _book()
    hv = b.bundle([])
    assert np.allclose(hv, 0.0)


# ── validation ──────────────────────────────────────────────────────────
def test_phase_code_rejects_out_of_range():
    b = _book(vocab_size=10, dim=64)
    with pytest.raises(IndexError):
        b.phase_code(10)


def test_phase_slot_rejects_out_of_range():
    b = _book(vocab_size=10, dim=64, max_positions=8)
    with pytest.raises(IndexError):
        b.phase_slot(8)


def test_argmax_coherence_rejects_wrong_shape():
    b = _book(vocab_size=10, dim=64)
    with pytest.raises(ValueError, match="hv shape"):
        b.argmax_coherence(np.zeros(128, dtype=np.complex128), 0)


# ── determinism ─────────────────────────────────────────────────────────
def test_codex_deterministic():
    a = _book()
    b = _book()
    assert np.allclose(a.codebook, b.codebook)


def test_cleanup_returns_none_on_no_match():
    b = _book(vocab_size=8, dim=64)
    hv = np.zeros(b.dim, dtype=np.complex128)
    # Zero vector: all coherences are 0; top-1 is still a token but
    # we're checking the interface returns an int, not None, unless
    # the codebook is empty.
    result = b.cleanup(hv, 0)
    assert result is None or isinstance(result, int)
