"""Legions: bounded tools that serve under one Kin.

A Kin is a role class with its own constraints. A legion is one tool
registered on that Kin. It inherits the Kin's gate: risk_classify,
evidence_attach, and the budget check. It is callable only through that
Kin's catalogue. There is no global registry for callers.

Legions do not bypass the residual core, Zeus routing, the Hades
checkpoint boundary, or the verified-cycle mouth policy. Kin serve under
the residual core. Example legions stay unregistered until a test or an
operator turns them on. Nothing here imports LangChain, AutoGen, crewAI,
or MetaGPT, and nothing here opens a network socket.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from resileos.harness.packet import ControlPacket
from resileos.harness.tools import (
    budget_and_stuck_guard,
    confidence_route,
    evidence_attach,
    risk_classify,
    verify_on_stop,
)
from resileos.kin.hades import Hades

ToolFn = Callable[..., Any]

# Role constraints. A legion may not ask for more than its Kin allows.
_KIN: dict[str, dict[str, bool]] = {
    "iris": {
        "writes_residual": False,
        "executes": True,
        "may_set_verified": False,
        "sees_history": True,
        "gated_write": False,
    },
    "metis": {
        "writes_residual": False,
        "executes": False,
        "may_set_verified": False,
        "sees_history": False,
        "gated_write": False,
    },
    "hermes": {
        "writes_residual": False,
        "executes": True,
        "may_set_verified": False,
        "sees_history": False,
        "gated_write": False,
    },
    "hades": {
        "writes_residual": False,
        "executes": True,
        "may_set_verified": False,
        "sees_history": False,
        "gated_write": False,
    },
    "apollo": {
        "writes_residual": False,
        "executes": True,
        "may_set_verified": True,
        "sees_history": True,
        "gated_write": False,
    },
    "eat": {
        "writes_residual": True,
        "executes": True,
        "may_set_verified": False,
        "sees_history": False,
        "gated_write": True,
    },
    "aphrodite": {
        "writes_residual": False,
        "executes": True,
        "may_set_verified": False,
        "sees_history": False,
        "gated_write": False,
    },
}

_ALIASES = {"perception": "eat"}

# Per-Kin surfaces. Not returned as a whole.
_surfaces: dict[str, dict[str, Callable[..., Any]]] = {}


class LegionError(Exception):
    """A legion tried to leave its Kin."""


def _canon(kin_name: str) -> str:
    name = (kin_name or "").strip().lower()
    name = _ALIASES.get(name, name)
    if name not in _KIN:
        raise LegionError(f"unknown kin: {kin_name}")
    return name


def reset_legions() -> None:
    """Drop registered legions. Tests use this. It does not list them."""
    _surfaces.clear()


def list_legions() -> dict[str, list[dict[str, str]]]:
    """Every Kin catalogue, including empty ones."""
    return {kin: kin_catalogue(kin) for kin in _KIN}


def kin_catalogue(kin_name: str) -> list[dict[str, str]]:
    """Names on this Kin only."""
    kin = _canon(kin_name)
    surface = _surfaces.get(kin, {})
    return [
        {
            "name": name,
            "kin": kin,
            "description": (fn.__doc__ or name).strip().split("\n")[0],
        }
        for name, fn in surface.items()
    ]


def _owned_by_other(tool_name: str, kin: str) -> bool:
    for other, surface in _surfaces.items():
        if other != kin and tool_name in surface:
            return True
    return False


def _as_dict(packet: Any) -> dict[str, Any]:
    if isinstance(packet, ControlPacket):
        return packet.to_dict()
    if isinstance(packet, dict):
        return packet
    raise LegionError("legion packet must be a ControlPacket or a dict")


def _refuse_bypass(kwargs: dict[str, Any]) -> None:
    if kwargs.get("residual_core") is not None or kwargs.get("bypass_core"):
        raise LegionError("a legion cannot own or bypass the residual core")
    if kwargs.get("zeus") is not None or kwargs.get("bypass_zeus"):
        raise LegionError("a legion cannot bypass Zeus routing")
    if kwargs.get("bypass_hades") or kwargs.get("restore_history"):
        raise LegionError("a legion cannot bypass the Hades checkpoint boundary")
    if kwargs.get("bypass_mouth") or kwargs.get("force_mouth"):
        raise LegionError("a legion cannot bypass the verified-cycle mouth policy")


def _wrap(kin: str, name: str, tool_fn: ToolFn, constraints: dict[str, Any]) -> Callable[..., Any]:
    role = _KIN[kin]
    action_default = str(constraints.get("action") or name)

    def wrapped(packet: Any, **kwargs: Any) -> dict[str, Any]:
        _refuse_bypass(kwargs)
        view = _as_dict(packet)
        host = packet if isinstance(packet, dict) else view
        action = str(kwargs.get("action", action_default))
        risk = risk_classify(action, None)
        if risk["risk_class"] == "deny":
            raise LegionError(f"risk deny: {risk['reason']}")
        if risk["risk_class"] == "ask" and kin != "metis":
            raise LegionError("risk ask: a legion does not execute an ask")

        guard = budget_and_stuck_guard(
            {
                "budget_remaining": dict(view.get("budget_remaining") or {}),
                "history": [],
            }
        )
        if not guard["ok"]:
            raise LegionError(f"over budget: {guard['reason']}")

        if constraints.get("escalate_only"):
            probability = kwargs.get("probability", view.get("confidence") or 0.0)
            route = confidence_route({"probability": float(probability)})
            if route["route"] != "escalate_or_abstain":
                raise LegionError(
                    f"{name} is escalate-only: reachable only when confidence_route says escalate"
                )

        if kin == "iris" and (kwargs.get("write_residual") or kwargs.get("learn_fn")):
            raise LegionError("iris legion cannot write residual state")
        if kin == "metis" and (kwargs.get("execute") or kwargs.get("learn_fn")):
            raise LegionError("metis legion cannot execute")
        if kin != "eat" and kwargs.get("learn_fn"):
            raise LegionError("learn is gated to the eat legion")

        if not role["sees_history"]:
            seen = {
                "id": view.get("id"),
                "artefact": kwargs.get("artefact", view.get("artefact")),
                "lesson": kwargs.get("lesson", view.get("lesson")),
                "budget_remaining": view.get("budget_remaining"),
                "verified": False,
            }
        else:
            seen = view

        safe_kwargs = {
            key: value
            for key, value in kwargs.items()
            if key
            not in {
                "residual_core",
                "zeus",
                "bypass_zeus",
                "bypass_core",
                "bypass_hades",
                "bypass_mouth",
                "force_mouth",
                "restore_history",
                "learn_fn",
                "execute",
                "write_residual",
                "history",
                "author_notes",
            }
        }
        produced = tool_fn(seen, **safe_kwargs)
        if not isinstance(produced, dict):
            produced = {"result": produced}

        if kin == "metis":
            result = {
                "executed": False,
                "policy": {
                    key: value
                    for key, value in produced.items()
                    if key not in {"allow_mouth", "verified", "learn"}
                },
                "risk": risk,
            }
        else:
            result = dict(produced)
            result["risk"] = risk

        if role["may_set_verified"]:
            apollo = kwargs.get("apollo_result")
            if not isinstance(apollo, dict):
                apollo = {"success": False}
            verdict = verify_on_stop(view, apollo)
            result["verify_on_stop"] = verdict
            verified = bool(verdict.get("verified"))
        else:
            verified = False
            result.pop("verify_on_stop", None)
        result["verified"] = verified
        if isinstance(packet, dict):
            packet["verified"] = verified

        if kin == "eat" and kwargs.get("learn_fn") and risk["risk_class"] == "allow":
            learn_fn = kwargs["learn_fn"]
            for claim in result.get("claims") or []:
                if isinstance(claim, (list, tuple)) and len(claim) >= 3:
                    learn_fn(str(claim[0]), str(claim[1]), str(claim[2]))
            result["gated_write"] = True
        else:
            result["gated_write"] = False

        evidence_attach(
            {"tool": name, "risk_class": risk["risk_class"], "verified": verified},
            f"legion:{kin}:{name}",
            host,
        )
        result["mouth_changed"] = False
        result.pop("allow_mouth", None)
        result["kin"] = kin
        return result

    wrapped.__name__ = name
    wrapped.__doc__ = tool_fn.__doc__ or name
    wrapped.spawns_processes = bool(constraints.get("spawns_processes"))  # type: ignore[attr-defined]
    return wrapped


def register_legion(
    kin_name: str,
    tool_fn: ToolFn,
    *,
    constraints: dict[str, Any],
    name: str | None = None,
) -> str:
    """Register one tool on one Kin. The constraints cannot exceed the role."""
    if not isinstance(constraints, dict):
        raise LegionError("constraints must be a dict")
    from resileos.kin.demigods.hierarchy import DemigodHierarchyError, active_demigod

    if active_demigod() is not None:
        raise DemigodHierarchyError(
            "a demigod cannot promote a temporary legion to permanent status"
        )
    try:
        from resileos.kin.demigods.swarm import swarm_mounted
    except ImportError:
        swarm_mounted = None
    if swarm_mounted is not None and swarm_mounted():
        raise DemigodHierarchyError(
            "a demigod cannot promote a temporary legion to permanent status"
        )
    kin = _canon(kin_name)
    role = _KIN[kin]
    if constraints.get("writes_residual") and not role["writes_residual"]:
        raise LegionError(f"{kin} legion cannot write residual state")
    if constraints.get("executes") and not role["executes"]:
        raise LegionError(f"{kin} legion cannot execute")
    if constraints.get("may_set_verified") and not role["may_set_verified"]:
        raise LegionError(f"{kin} legion cannot mark verified")
    tool_name = name or getattr(tool_fn, "__name__", None) or "legion"
    surface = _surfaces.setdefault(kin, {})
    surface[tool_name] = _wrap(kin, tool_name, tool_fn, constraints)
    return tool_name


def legion_spawns(kin_name: str, tool_name: str) -> bool:
    """True when this Kin's legion declared that it can spawn processes."""
    kin = _canon(kin_name)
    fn = _surfaces.get(kin, {}).get(tool_name)
    return bool(getattr(fn, "spawns_processes", False))


def invoke_legion(kin_name: str, tool_name: str, packet: Any, **kwargs: Any) -> dict[str, Any]:
    """Call a tool on this Kin's surface. Other Kin's tools are refused."""
    kin = _canon(kin_name)
    surface = _surfaces.get(kin, {})
    if tool_name not in surface:
        if _owned_by_other(tool_name, kin):
            raise LegionError(f"cross-kin call refused: {tool_name} is not on {kin}")
        raise LegionError(f"unknown legion {tool_name} for {kin}")
    return surface[tool_name](packet, **kwargs)


def register_example_legions(
    *,
    enable: bool = False,
    inference_fn: Callable[..., Any] | None = None,
    trace_path: str | None = None,
    lesson_path: str | None = None,
) -> list[str]:
    """Optional examples. Off unless enable is true. No network calls."""
    if not enable:
        return []
    registered: list[str] = []

    def ollama_local(seen: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Local inference placeholder. The caller supplies inference_fn."""
        fn = inference_fn or kwargs.get("inference_fn")
        if not callable(fn):
            raise LegionError("ollama example requires an injected inference_fn")
        text = fn(kwargs.get("prompt", ""))
        return {"text": text, "backend": "injected", "network": False}

    registered.append(
        register_legion(
            "hermes",
            ollama_local,
            name="ollama_local",
            constraints={
                "action": "local inference",
                "writes_residual": False,
                "executes": True,
                "escalate_only": True,
            },
        )
    )

    def jsonl_read(seen: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Read a JSONL trace. Does not write residual state."""
        path = trace_path or kwargs.get("trace_path")
        if not path:
            return {"lines": [], "wrote": False}
        lines = []
        try:
            with open(path, encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        lines.append(json.loads(line))
        except FileNotFoundError:
            lines = []
        return {"lines": lines, "wrote": False, "vector_store": False}

    def jsonl_append(seen: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Append one JSON object to a trace file. Not a vector store."""
        path = trace_path or kwargs.get("trace_path")
        if not path:
            raise LegionError("jsonl trace requires a path")
        record = kwargs.get("record") or {"event": "trace"}
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        return {"appended": True, "vector_store": False}

    registered.append(
        register_legion(
            "iris",
            jsonl_read,
            name="jsonl_trace",
            constraints={"action": "read trace", "writes_residual": False, "executes": True},
        )
    )
    registered.append(
        register_legion(
            "hades",
            jsonl_append,
            name="jsonl_trace",
            constraints={"action": "read trace", "writes_residual": False, "executes": True},
        )
    )

    def lesson_notes(seen: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Append one line to the lesson file. No vector store."""
        path = lesson_path or kwargs.get("lesson_path")
        if not path:
            raise LegionError("lesson notes require a path")
        note = str(kwargs.get("note") or seen.get("lesson") or "")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(note + "\n")
        return {"appended": True, "vector_store": False, "chars": len(note)}

    registered.append(
        register_legion(
            "hades",
            lesson_notes,
            name="lesson_notes",
            constraints={"action": "append lesson", "writes_residual": False, "executes": True},
        )
    )

    def action_placeholder(seen: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Placeholder for a code or action tool. Does not execute code."""
        return {
            "placeholder": True,
            "executed_code": False,
            "action": kwargs.get("action"),
            "artefact": seen.get("artefact"),
            "lesson": seen.get("lesson"),
            "saw_history": "history" in seen,
        }

    for kin in ("hermes", "apollo"):
        registered.append(
            register_legion(
                kin,
                action_placeholder,
                name="action_placeholder",
                constraints={
                    "action": "inspect",
                    "writes_residual": False,
                    "executes": True,
                    "may_set_verified": kin == "apollo",
                },
            )
        )

    def restore_checkpoint(seen: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Restore through Hades.restore_fresh. History and scars stay behind."""
        store = kwargs.get("hades")
        if not isinstance(store, Hades):
            raise LegionError("restore requires a Hades store")
        fresh = store.restore_fresh(str(kwargs.get("checkpoint_id") or ""))
        return {
            "id": fresh.id,
            "history": list(fresh.history),
            "scars": list(fresh.scars),
            "verified": fresh.verified,
            "lesson": next(
                (
                    event.get("lesson")
                    for event in fresh.history
                    if isinstance(event, dict) and event.get("lesson")
                ),
                None,
            ),
        }

    registered.append(
        register_legion(
            "hades",
            restore_checkpoint,
            name="restore_fresh",
            constraints={"action": "restore", "writes_residual": False, "executes": True},
        )
    )
    return registered
