""" Resileos-QAI substrate package.

Two-head system for QD-TER bridge integration, plus support utilities:
    geometry.py         Head 1: geometric manifold tracking (RES-601)
    reduction.py        Head 2: FEP reduction tracking (RES-600)
    spd.py              positive-definiteness helpers (RES-601 §7 item 3)
    fpe.py              FPE backend selector (leCore / in-house)
    rheology.py         interface for the coordinate map (unbound)
    nonconservative.py  non-conservative diagonal operator (RES-200 §ext)
    oscillator.py       Kuramoto phase field (RES-200 §ext)
    phasor.py           phasor graph, band carriers, banded memory (RES-306)
    sandbox.py          Causal Sandbox Index (RES-305)
    agency.py           heuristic routing layer (RES-307)
    constructive.py     constructive direction head (RES-308)
"""
from .geometry import (
    LowRankMetricHead,
    BridgeMetricHead,
    CandidateBridgeMetricHead,
    CandidateScalars,
)
from .reduction import (
    VerifiableFEPReductionHead,
    coherence_schedule,
    simulate_axiom_d,
    simulate_linear_ode,
)
from .spd import assert_spd, is_spd, min_eigenvalue, isotropic_metric
from .fpe import fpe_encode_bipolar, backend_name, LECORE_AVAILABLE
from .nonconservative import NonConservativeOperator
from .oscillator import (
    KuramotoField,
    golden_ladder,
    golden_weyl,
    coupling_from_graph,
)
from .phasor import (
    PhasorGraph,
    BandCarriers,
    BandedMemory,
    phase_from_names,
)
from .sandbox import (
    volume_residual,
    internal_prediction_error,
    compute_csi,
    CSIState,
    fast_confidence,
)
from .agency import AgencyChild, AgencyGroup, HandlerFn
from .constructive import ConstructiveHead

__all__ = [
    # geometry
    "LowRankMetricHead",
    "BridgeMetricHead",
    "CandidateBridgeMetricHead",
    "CandidateScalars",
    # reduction
    "VerifiableFEPReductionHead",
    "coherence_schedule",
    "simulate_axiom_d",
    "simulate_linear_ode",
    # spd
    "assert_spd",
    "is_spd",
    "min_eigenvalue",
    "isotropic_metric",
    # fpe
    "fpe_encode_bipolar",
    "backend_name",
    "LECORE_AVAILABLE",
    # nonconservative
    "NonConservativeOperator",
    # oscillator
    "KuramotoField",
    "golden_ladder",
    "golden_weyl",
    "coupling_from_graph",
    # phasor
    "PhasorGraph",
    "BandCarriers",
    "BandedMemory",
    "phase_from_names",
    # sandbox
    "volume_residual",
    "internal_prediction_error",
    "compute_csi",
    "CSIState",
    "fast_confidence",
    # agency
    "AgencyChild",
    "AgencyGroup",
    "HandlerFn",
    # constructive
    "ConstructiveHead",
    # SDM / Hopfield (RES-317)
    "AttractorMemory",
    "HopfieldConfig",
    "KanervaSDM",
    "ModernHopfield",
    "SDMConfig",
    # Multi-engine composition (RES-318)
    "CoupledPacket",
    "CouplingField",
    "CoupledStreamGenerator",
    "EngineGroup",
]

# Lazy exports avoid circular imports (core ↔ engine_group).
_LAZY = {
    "AttractorMemory": (".sdm", "AttractorMemory"),
    "HopfieldConfig": (".sdm", "HopfieldConfig"),
    "KanervaSDM": (".sdm", "KanervaSDM"),
    "ModernHopfield": (".sdm", "ModernHopfield"),
    "SDMConfig": (".sdm", "SDMConfig"),
    "CoupledPacket": (".coupling", "CoupledPacket"),
    "CouplingField": (".coupling", "CouplingField"),
    "CoupledStreamGenerator": (".engine_group", "CoupledStreamGenerator"),
    "EngineGroup": (".engine_group", "EngineGroup"),
}


def __getattr__(name: str):
    if name in _LAZY:
        import importlib
        mod_name, attr = _LAZY[name]
        mod = importlib.import_module(mod_name, __name__)
        val = getattr(mod, attr)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
