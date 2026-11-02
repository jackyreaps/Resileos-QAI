"""Capacity contract unit tests."""
from __future__ import annotations

import pytest

from resileos.capacity import (
    RESIDUAL_BLOCK,
    CapacityConfig,
    admit_scale,
    hopfield_cap,
    should_use_learn_many,
)


def test_residual_block_is_64():
    assert RESIDUAL_BLOCK == 64


def test_default_hf_cap_is_block_multiple():
    c = CapacityConfig()
    assert c.hf_cap == 64 * 16
    assert hopfield_cap(c) == c.hf_cap


def test_hf_cap_scales_with_blocks():
    c = CapacityConfig(hf_cap_blocks=32)
    assert c.hf_cap == 2048


def test_learn_many_threshold():
    c = CapacityConfig(require_learn_many_above=256)
    assert not should_use_learn_many(255, c)
    assert should_use_learn_many(256, c)


def test_admit_scale():
    c = CapacityConfig(min_probe_hit_rate=1.0)
    assert admit_scale(1.0, c)
    assert not admit_scale(0.99, c)


def test_invalid_config():
    with pytest.raises(ValueError):
        CapacityConfig(hf_cap_blocks=0)
