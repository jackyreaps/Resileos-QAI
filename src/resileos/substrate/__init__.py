"""Resileos-QAI substrate package.

Two-head system for QD-TER bridge integration:
    geometry.py   — Head 1: geometric manifold tracking (RES-601)
    reduction.py  — Head 2: FEP reduction tracking (RES-600)
    spd.py        — positive-definiteness helpers (RES-601 §7 item 3)
"""
from .geometry import LowRankMetricHead, BridgeMetricHead
from .reduction import (
    VerifiableFEPReductionHead,
    coherence_schedule,
    simulate_axiom_d,
    simulate_linear_ode,
)
from .spd import assert_spd, is_spd, isotropic_metric

__all__ = [
    "LowRankMetricHead",
    "BridgeMetricHead",
    "assert_spd",
    "is_spd",
    "isotropic_metric",
    "VerifiableFEPReductionHead",
    "coherence_schedule",
    "simulate_axiom_d",
    "simulate_linear_ode",
]
