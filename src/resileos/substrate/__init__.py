"""Resileos-QAI substrate package.

Two-head system for QD-TER bridge integration:
    geometry.py   — Head 1: geometric manifold tracking (RES-601)
    reduction.py  — Head 2: FEP reduction tracking (RES-600)
"""
from .geometry import LowRankMetricHead, BridgeMetricHead
from .reduction import (
    VerifiableFEPReductionHead,
    simulate_axiom_d,
    simulate_linear_ode,
)

__all__ = [
    "LowRankMetricHead",
    "BridgeMetricHead",
    "VerifiableFEPReductionHead",
    "simulate_axiom_d",
    "simulate_linear_ode",
]
