"""Hierarchical encoding for the composition layer (RES-310).

Exports the encoder (RES-310), the query descent (RES-310), and the
streaming state (RES-311).
"""
from .encoder import (
    HierarchicalEncoder,
    HierarchicalPacket,
    default_capacity,
    level_phasor,
)
from .query import HierarchicalQuery
from .stream import StreamState, StreamStateConfig

__all__ = [
    "HierarchicalEncoder",
    "HierarchicalPacket",
    "HierarchicalQuery",
    "StreamState",
    "StreamStateConfig",
    "default_capacity",
    "level_phasor",
]
