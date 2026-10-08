"""
Resileos-QAI — Hybrid Classical Residual Core + HDRIFT Generative Substrate.

Documentation: docs/README.md (RES-000)
Layer ownership:
    RES-200/201/202  classical core, packet, canonicalization
    RES-300..303     HDRIFT adapter, moments, abstention, sigma gate
    RES-400..402     run config, training, validation
"""
from .packet import Packet, canonical_json, packet_hash
from .moments import Seeds, build_moments
from .adapter import HDRIFTAdapter
from .abstention import AbstentionInputs, AbstentionThresholds, route_signals
from .sigma import SigmaGate, SigmaAction

__all__ = [
    "Packet", "canonical_json", "packet_hash",
    "Seeds", "build_moments",
    "HDRIFTAdapter",
    "AbstentionInputs", "AbstentionThresholds", "route_signals",
    "SigmaGate", "SigmaAction",
]

__version__ = "1.0.0"
