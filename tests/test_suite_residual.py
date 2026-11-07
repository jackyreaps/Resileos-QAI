"""Tests for the public residual hook."""
import os

from resileos.ui.suite_residual import suite_residual


def test_placeholder_without_env(monkeypatch):
    monkeypatch.delenv("RESILEOS_RESIDUAL_IMPL", raising=False)
    label = suite_residual(0.8, 0.2, belt=1)
    assert label.startswith("r")
    assert label == suite_residual(0.8, 0.2, belt=1)


def test_bad_impl_falls_back(monkeypatch):
    monkeypatch.setenv("RESILEOS_RESIDUAL_IMPL", "no.such.mod:fn")
    label = suite_residual(0.1, 0.1, belt=0)
    assert label.startswith("r")
