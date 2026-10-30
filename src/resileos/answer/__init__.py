"""Answer backends for /api/v1/answer (RES-327)."""

from .native_encode import GateSelection, encode_gate, encode_question
from .tools_schema import list_tool_schemas, openai_tools, frame_index
from .policy import (
    prefer_child,
    gbx_bypass_recurrent,
    derive_frame,
    frame_to_tool_tag,
)
from .frame_telemetry import frame_histogram, record_frame
from .tool_execute import execute_tool
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
    "list_tool_schemas",
    "openai_tools",
    "frame_index",
    "prefer_child",
    "gbx_bypass_recurrent",
    "derive_frame",
    "frame_to_tool_tag",
    "frame_histogram",
    "record_frame",
    "execute_tool",
]
