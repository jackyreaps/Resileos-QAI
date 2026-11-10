"""Demi-god skills — loadable specialists under the Kin hierarchy.

Summoning injects a bounded guide into the caller's ControlPacket.
They serve; they do not rule. The persona text lives in ``guides/``.
The checks live in ``checks.py`` and are ordinary Python.
"""
from .checks import hephaestus_check, momus_review, nike_check, themis_check
from .hierarchy import (
    DemigodError,
    DemigodHierarchyError,
    active_demigod,
    demigod_duty,
    durable_cross_attempt,
    refuse_learn,
    refuse_residual_ownership,
    residual_hash_only,
)
from .results import Defect, DemigodResult
from .router import demigod_dismiss, demigod_search, demigod_summon, list_demigods

__all__ = [
    "Defect",
    "DemigodError",
    "DemigodHierarchyError",
    "DemigodResult",
    "active_demigod",
    "demigod_dismiss",
    "demigod_duty",
    "demigod_search",
    "demigod_summon",
    "durable_cross_attempt",
    "hephaestus_check",
    "list_demigods",
    "momus_review",
    "nike_check",
    "refuse_learn",
    "refuse_residual_ownership",
    "residual_hash_only",
    "themis_check",
]
