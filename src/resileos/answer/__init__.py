"""Answer backends for /api/v1/answer (RES-327)."""

from .native_encode import GateSelection, encode_gate, encode_question
from .backends import (
    AnswerBackend,
    AnswerContext,
    HostedBackend,
    LocalHFBackend,
    StructuredBackend,
    build_backend,
    build_prompt,
    context_from_answer,
    humanize_relation,
    list_backends,
    question_from_context,
    select_backend,
)

__all__ = [
    "AnswerBackend",
    "AnswerContext",
    "HostedBackend",
    "LocalHFBackend",
    "StructuredBackend",
    "build_backend",
    "build_prompt",
    "context_from_answer",
    "humanize_relation",
    "list_backends",
    "question_from_context",
    "select_backend",
    "encode_question",
    "encode_gate",
    "GateSelection",
]
