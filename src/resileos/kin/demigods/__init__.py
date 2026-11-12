"""Demi-god skills — loadable specialists under the Kin hierarchy.

Summoning injects a bounded guide into the caller's ControlPacket.
They serve; they do not rule. The persona text lives in ``guides/``.
The checks live in ``checks.py`` and are ordinary Python.
"""
from .checks import (
    MAX_NEED_MORE_ROUNDS,
    apply_blind_supplement,
    atlas_check,
    hephaestus_check,
    momus_review,
    nike_check,
    themis_check,
)
from .hierarchy import (
    DemigodError,
    DemigodHierarchyError,
    active_demigod,
    demigod_duty,
    durable_cross_attempt,
    promote_temporary,
    refuse_learn,
    refuse_residual_ownership,
    residual_hash_only,
)
from .results import (
    NEED_MISSING_REQUIREMENT,
    NEED_MISSING_RESIDUAL_HASH,
    NEED_MISSING_SPEC_FIELD,
    OUTCOME_APPROVED,
    OUTCOME_FAIL,
    OUTCOME_NEED_MORE,
    Defect,
    DemigodResult,
    NeedMore,
)
from .router import demigod_dismiss, demigod_search, demigod_summon, list_demigods
from .swarm import demigod_attempt, demigod_stop, swarm_surface

__all__ = [
    "Defect",
    "DemigodError",
    "DemigodHierarchyError",
    "DemigodResult",
    "MAX_NEED_MORE_ROUNDS",
    "NEED_MISSING_REQUIREMENT",
    "NEED_MISSING_RESIDUAL_HASH",
    "NEED_MISSING_SPEC_FIELD",
    "NeedMore",
    "OUTCOME_APPROVED",
    "OUTCOME_FAIL",
    "OUTCOME_NEED_MORE",
    "active_demigod",
    "apply_blind_supplement",
    "atlas_check",
    "demigod_attempt",
    "demigod_dismiss",
    "demigod_duty",
    "demigod_search",
    "demigod_stop",
    "demigod_summon",
    "durable_cross_attempt",
    "hephaestus_check",
    "list_demigods",
    "momus_review",
    "nike_check",
    "promote_temporary",
    "refuse_learn",
    "refuse_residual_ownership",
    "residual_hash_only",
    "swarm_surface",
    "themis_check",
]
