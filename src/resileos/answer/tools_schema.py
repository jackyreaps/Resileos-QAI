"""Tool JSON schemas for external mouths (RES-327 tools).

Frontier models call these tools; the substrate remains source of truth.
Schemas are JSON Schema draft-07 compatible and are aligned, where
useful, with Human-Medium *frames* (interpretive regulators that bias
which moves are legible). Frame ids are labels for later mapping to
docs such as ``adjacent/gnosis_frame.md`` — not runtime enforcement.
"""
from __future__ import annotations

from typing import Any


# Frame tags (Human-Medium §10): optional metadata for operators.
FRAME_GNOSIS = "gnosis"          # high-coherence / truth-seeking bias
FRAME_OPERATIONAL = "operational"  # exact store ops, no interpretive overlay
FRAME_ABSTAIN = "abstain"        # none-channel / recovery refusal


TOOL_ASK: dict[str, Any] = {
    "name": "resileos_ask",
    "description": (
        "Exact relational lookup against the Titanos band store. "
        "Returns stored object(s) for (subject, relation) or the inverse. "
        "Does not invent facts. Prefer this for single-hop attributes."
    ),
    "frame": FRAME_OPERATIONAL,
    "sector_hint": "gbx_like",
    "parameters": {
        "type": "object",
        "properties": {
            "subject": {"type": "string", "description": "Entity name"},
            "relation": {"type": "string", "description": "Relation name"},
            "inverse": {
                "type": "boolean",
                "default": False,
                "description": "If true, query who points at subject via relation",
            },
        },
        "required": ["subject", "relation"],
        "additionalProperties": False,
    },
}

TOOL_CHAIN: dict[str, Any] = {
    "name": "resileos_chain",
    "description": (
        "Multi-hop path through the store. Pass an ordered list of "
        "relation hops starting from subject. Use for flexible / path "
        "questions (otx_like sector)."
    ),
    "frame": FRAME_OPERATIONAL,
    "sector_hint": "otx_like",
    "parameters": {
        "type": "object",
        "properties": {
            "subject": {"type": "string"},
            "hops": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 8,
                "description": "Ordered relation names",
            },
        },
        "required": ["subject", "hops"],
        "additionalProperties": False,
    },
}

TOOL_SPARQL: dict[str, Any] = {
    "name": "resileos_sparql",
    "description": (
        "Restricted SPARQL-like query over the in-memory fact graph. "
        "Exact structured retrieval only."
    ),
    "frame": FRAME_OPERATIONAL,
    "sector_hint": "otx_like",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Query string"},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}

TOOL_ABSTAIN: dict[str, Any] = {
    "name": "resileos_abstain",
    "description": (
        "Explicit none-channel. Call when the store has no reliable row "
        "or the recovery gate would refuse. Do not invent an answer."
    ),
    "frame": FRAME_ABSTAIN,
    "sector_hint": "",
    "parameters": {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "Short machine-readable reason",
            },
        },
        "required": [],
        "additionalProperties": False,
    },
}

TOOL_ANSWER: dict[str, Any] = {
    "name": "resileos_answer",
    "description": (
        "Gate-encoded free-text or structured retrieve + render through "
        "the framework mouth. Returns status ANSWERED | NO_ROWS | "
        "ABSTAINED | NONE_CHANNEL plus gate_capacity_bits."
    ),
    "frame": FRAME_GNOSIS,
    "sector_hint": "",
    "parameters": {
        "type": "object",
        "properties": {
            "question": {"type": "string"},
            "subject": {"type": "string"},
            "relation": {"type": "string"},
            "inverse": {"type": "boolean", "default": False},
        },
        "additionalProperties": False,
    },
}


def list_tool_schemas() -> list[dict[str, Any]]:
    """All tool schemas for OpenAI/Anthropic-style tool calling."""
    return [TOOL_ASK, TOOL_CHAIN, TOOL_SPARQL, TOOL_ABSTAIN, TOOL_ANSWER]


def openai_tools() -> list[dict[str, Any]]:
    """OpenAI function-calling envelope."""
    out = []
    for t in list_tool_schemas():
        out.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            },
        })
    return out


def frame_index() -> dict[str, list[str]]:
    """tool name -> frame id (for Human-Medium frame comparison)."""
    return {
        t["name"]: t.get("frame", FRAME_OPERATIONAL)
        for t in list_tool_schemas()
    }
