"""Hierarchical encoding for the composition layer (RES-310)."""

from .encoder import (
    HierarchicalEncoder,
    HierarchicalPacket,
    default_capacity,
    level_phasor,
)
from .query import HierarchicalQuery

__all__ = [
    "HierarchicalEncoder",
    "HierarchicalPacket",
    "HierarchicalQuery",
    "default_capacity",
    "level_phasor",
]
