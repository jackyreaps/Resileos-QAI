"""Hierarchical encoding for the composition layer (RES-310, RES-311, RES-312).

Exports:
    RES-310  HierarchicalEncoder, HierarchicalPacket, HierarchicalQuery
    RES-311  StreamState, StreamStateConfig
    RES-312  MaskStack, MaskStackConfig, MaskLayer, layer_carrier
"""
from .encoder import (
    HierarchicalEncoder,
    HierarchicalPacket,
    default_capacity,
    level_phasor,
)
from .query import HierarchicalQuery
from .stream import StreamState, StreamStateConfig
from .mask import (
    MaskStack,
    MaskStackConfig,
    MaskLayer,
    layer_carrier,
    exponent_for,
    FEATURE_BITS,
    K_MIN,
    DEFAULT_K,
)

__all__ = [
    # RES-310
    "HierarchicalEncoder",
    "HierarchicalPacket",
    "HierarchicalQuery",
    "default_capacity",
    "level_phasor",
    # RES-311
    "StreamState",
    "StreamStateConfig",
    # RES-312
    "MaskStack",
    "MaskStackConfig",
    "MaskLayer",
    "layer_carrier",
    "exponent_for",
    "FEATURE_BITS",
    "K_MIN",
    "DEFAULT_K",
]
