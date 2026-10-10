"""Resileos-QAI integration package.

Contains HTTP clients for external services that Resileos can consult
at runtime:

    lecore_client   — leCore VSA engine (capability router + invoker)
"""
from .lecore_client import (
    LeCoreClient,
    LeCoreUnreachable,
    LeCoreError,
    Capability,
    InvokeResult,
)

__all__ = [
    "LeCoreClient",
    "LeCoreUnreachable",
    "LeCoreError",
    "Capability",
    "InvokeResult",
]
