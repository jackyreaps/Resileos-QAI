"""Resileos-QAI substrate package.

Contains the two-head system for QD-TER bridge integration:
    geometry.py   — Head 1: geometric manifold tracking (RES-601)
    reduction.py  — Head 2: FEP reduction tracking (RES-600)
"""
from .geometry import LowRankMetricHead, BridgeMetricHead
from .reduction import VerifiableFEPReductionHead

__all__ = ["LowRankMetricHead", "BridgeMetricHead", "VerifiableFEPReductionHead"]
