"""Tests for the language pipeline."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.pipeline import (
    PipelineConfig,
    PipelineResult,
    LanguagePipeline,
    load_corpus,
)


def _cfg(**overrides):
    base = dict(
        dim=256,
        vocab_size=64,
        max_positions=64,
        m=16,
        n=16,
        r=8,
        n_residual_layers=4,
        reaper_n_saved=4,
        phi_compress_enabled=False,
        phi_compress_warmup=32,
        phi_compress_min_R=0.9,
        oscillator_kappa=1.0,
        oscillator_alpha=0.5,
        oscillator_dt=0.1,
        seed=0,
    )
    base.update(overrides)
    return PipelineConfig(**base)


def _pipeline(**overrides):
    return LanguagePipeline(_cfg(**overrides))


# ── config ──────────────────────────────────────────────────────────────
def test_config_validates_mn_equals_dim():
    with pytest.raises(ValueError, match="m\\*n"):
        # 10 * 9 = 90 ≠ 100
        PipelineConfig(dim=100, m=10, n=9).validate()


def test_config_rejects_r_too_large():
    with pytest.raises(ValueError, match="r must be"):
        PipelineConfig(dim=64, m=8, n=8, r=16).validate()


def test_config_from_json_roundtrip(tmp_path):
    cfg = _cfg()
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(cfg.to_dict()))
    cfg2 = PipelineConfig.from_json(p)
    assert cfg2.dim == cfg.dim
    assert cfg2.m == cfg.m and cfg2.n == cfg.n
    assert cfg2.r == cfg.r
    assert cfg2.phi_compress_warmup == cfg.phi_compress_warmup
    assert cfg2.phi_compress_min_R == cfg.phi_compress_min_R


# ── single token ────────────────────────────────────────────────────────
def test_pipeline_single_token_round_trip():
    p = _pipeline()
    result = p.step([5])
    assert isinstance(result, PipelineResult)
    assert result.recovered == [5]
    assert result.recovered_exactly is True


def test_pipeline_token_zero_round_trip():
    p = _pipeline()
    result = p.step([0])
    assert result.recovered == [0]


# ── sequences ───────────────────────────────────────────────────────────
def test_pipeline_short_sequence_round_trip():
    p = _pipeline()
    result = p.step([3, 5, 7])
    assert result.recovered == [3, 5, 7]
    assert result.recovered_exactly


def test_pipeline_longer_sequence():
    p = _pipeline(max_positions=32)
    seq = [1, 10, 20, 30, 40, 50]
    result = p.step(seq)
    assert result.recovered == seq


def test_pipeline_repeated_step_state_advances():
    p = _pipeline()
    a = p.step([1, 2, 3])
    b = p.step([1, 2, 3])
    assert a.order_parameter != b.order_parameter


# ── validation ──────────────────────────────────────────────────────────
def test_pipeline_rejects_empty_sequence():
    p = _pipeline()
    with pytest.raises(ValueError, match="non-empty"):
        p.step([])


def test_pipeline_rejects_out_of_range_token():
    p = _pipeline(vocab_size=16)
    with pytest.raises(ValueError, match="out of vocab"):
        p.step([5, 20])


def test_pipeline_rejects_too_long_sequence():
    p = _pipeline(max_positions=4)
    with pytest.raises(ValueError, match="max_positions"):
        p.step([0, 1, 2, 3, 4])


# ── reaper hook ─────────────────────────────────────────────────────────
def test_pipeline_reaper_ran():
    p = _pipeline(r=8, reaper_n_saved=4)
    result = p.step([1, 2, 3, 4])
    assert result.henad_count + result.nexus_count == p.cfg.r
    assert 0.0 <= result.reaper_fraction <= 1.0


# ── oscillator hook ─────────────────────────────────────────────────────
def test_pipeline_oscillator_advanced():
    p = _pipeline()
    r0 = p.field.order_parameter()
    for _ in range(5):
        p.step([3, 5])
    r1 = p.field.order_parameter()
    assert r1 != r0


def test_pipeline_gate_state_valid():
    p = _pipeline()
    result = p.step([1, 2])
    assert result.gate_state in ("LOCKED", "EXPLORING", "MIXED")


# ── φ-compress hook ─────────────────────────────────────────────────────
def test_pipeline_phi_compress_no_op_when_disabled():
    p = _pipeline(phi_compress_enabled=False)
    for _ in range(10):
        p.step([1, 2])
    assert p.core.cfg.r == 8
    assert p.stats()["compressions"] == []


def test_pipeline_phi_compress_respects_warmup():
    p = _pipeline(phi_compress_enabled=True, phi_compress_warmup=10)
    for _ in range(5):
        p.step([1, 2])
    assert p.stats()["compressions"] == []


def test_pipeline_last_R_starts_at_zero():
    p = _pipeline()
    assert p._last_R == 0.0


def test_pipeline_phi_compress_fires_after_warmup_and_lock():
    p = _pipeline(
        phi_compress_enabled=True,
        phi_compress_warmup=0,
        phi_compress_min_R=0.0,
    )
    p.step([1, 2])
    p._last_R = 0.95
    p.step([1, 2])
    assert len(p.stats()["compressions"]) >= 1


# ── result serialization ────────────────────────────────────────────────
def test_result_to_dict_keys():
    p = _pipeline()
    result = p.step([1, 2, 3])
    d = result.to_dict()
    for k in (
        "input_tokens", "recovered", "reaper_fraction", "nexus_count",
        "henad_count", "rank_used", "order_parameter", "epsilon",
        "gate_state", "reconstruction_rel_error",
    ):
        assert k in d


# ── corpus loader ───────────────────────────────────────────────────────
def test_load_corpus_parses_lines(tmp_path):
    p = tmp_path / "c.txt"
    p.write_text("1,2,3\n# comment\n\n5,6\n")
    seqs = load_corpus(p)
    assert seqs == [[1, 2, 3], [5, 6]]


def test_load_corpus_empty(tmp_path):
    p = tmp_path / "c.txt"
    p.write_text("# only comments\n\n")
    assert load_corpus(p) == []


# ── stats ───────────────────────────────────────────────────────────────
def test_pipeline_stats_shape():
    p = _pipeline()
    p.step([1, 2])
    s = p.stats()
    for k in ("step_count", "compressions", "current_rank", "last_R", "field_r"):
        assert k in s
    assert s["step_count"] == 1
