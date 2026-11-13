"""Temporary swarm bound to one Demi-god summon.

The swarm lives on the attempt. It is not a Kin catalogue and it is not
a second summon API. Dismiss, or the end of ``demigod_attempt``, drops it.
"""
from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from resileos.harness.packet import ControlPacket
from resileos.harness.tools import budget_and_stuck_guard, evidence_attach, risk_classify
from resileos.kin.legions import LegionError, invoke_legion, kin_catalogue, legion_spawns
from resileos.kin.moirai import note_worker, reserve_spawner, stop_owner

from .hierarchy import DemigodError, DemigodHierarchyError

# Hephaestus is the Studio patron and is not a Kin. Forge and the
# plan/test/debug loop register on Hermes (paths and dispatch).
# Themis and Nike serve Apollo (proof). Momus serves Hermes.
# Atlas serves Iris. Eat is the ingest Kin; no Demi-god parent is Eat.
PARENT_KIN = {
    "themis": "apollo",
    "momus": "hermes",
    "hephaestus": "hermes",
    "atlas": "iris",
    "nike": "apollo",
    "morpheus": "hades",
}

_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
SWARM_KEY = "demigod_swarm"

_STRIP = {
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


def _joint_note(seen: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Check-local joint note. It is not a catalogue legion."""
    del seen
    return {
        "note": str(kwargs.get("note") or "joints"),
        "temporary": True,
        "writes_residual": False,
    }


CHECK_LOCAL: dict[str, dict[str, Callable[..., Any]]] = {
    "hephaestus": {"joint_note": _joint_note},
}


@dataclass
class _Attempt:
    attempt_id: str
    demigod: str
    parent_kin: str
    names: list[str]
    surface: dict[str, Callable[..., Any]]


_ATTEMPTS: dict[str, _Attempt] = {}


def swarm_mounted() -> bool:
    return bool(_ATTEMPTS)


def _packet_id(packet: Any) -> str:
    if isinstance(packet, ControlPacket):
        return str(packet.id)
    if isinstance(packet, dict) and packet.get("id"):
        return str(packet["id"])
    return "attempt"


def swarm_meta(packet: Any) -> dict[str, Any] | None:
    if isinstance(packet, ControlPacket):
        meta = packet.state.get(SWARM_KEY)
        return meta if isinstance(meta, dict) else None
    if isinstance(packet, dict):
        meta = packet.get(SWARM_KEY)
        if isinstance(meta, dict):
            return meta
        state = packet.get("state")
        if isinstance(state, dict) and isinstance(state.get(SWARM_KEY), dict):
            return state[SWARM_KEY]
    return None


def _set_swarm(packet: Any, meta: dict[str, Any]) -> None:
    if isinstance(packet, ControlPacket):
        packet.state[SWARM_KEY] = meta
        return
    if not isinstance(packet, dict):
        raise DemigodError("demigod swarm requires a packet")
    packet[SWARM_KEY] = meta
    state = packet.get("state")
    if isinstance(state, dict):
        state[SWARM_KEY] = meta


def _pop_swarm(packet: Any) -> dict[str, Any] | None:
    if isinstance(packet, ControlPacket):
        meta = packet.state.pop(SWARM_KEY, None)
        return meta if isinstance(meta, dict) else None
    if isinstance(packet, dict):
        meta = packet.pop(SWARM_KEY, None)
        state = packet.get("state")
        if isinstance(state, dict) and SWARM_KEY in state:
            state_meta = state.pop(SWARM_KEY, None)
            if not isinstance(meta, dict):
                meta = state_meta
        return meta if isinstance(meta, dict) else None
    return None


def _refuse_bypass(kwargs: dict[str, Any]) -> None:
    if kwargs.get("residual_core") is not None or kwargs.get("bypass_core"):
        raise LegionError("a legion cannot own or bypass the residual core")
    if kwargs.get("zeus") is not None or kwargs.get("bypass_zeus"):
        raise LegionError("a legion cannot bypass Zeus routing")
    if kwargs.get("bypass_hades") or kwargs.get("restore_history"):
        raise LegionError("a legion cannot bypass the Hades checkpoint boundary")
    if kwargs.get("bypass_mouth") or kwargs.get("force_mouth"):
        raise LegionError("a legion cannot bypass the verified-cycle mouth policy")
    if kwargs.get("learn_fn") or kwargs.get("write_residual"):
        raise LegionError("learn is gated to the eat legion")


def _view(packet: Any) -> dict[str, Any]:
    if isinstance(packet, ControlPacket):
        return packet.to_dict()
    if isinstance(packet, dict):
        return packet
    raise LegionError("legion packet must be a ControlPacket or a dict")


def _gated_helper(
    kin: str,
    name: str,
    fn: Callable[..., Any],
    packet: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    """Parent-Kin gates for a helper that is not in the catalogue."""
    _refuse_bypass(kwargs)
    view = _view(packet)
    action = str(kwargs.get("action") or "inspect")
    risk = risk_classify(action, None)
    if risk["risk_class"] == "deny":
        raise LegionError(f"risk deny: {risk['reason']}")
    if risk["risk_class"] == "ask" and kin != "metis":
        raise LegionError("risk ask: a legion does not execute an ask")
    guard = budget_and_stuck_guard(
        {"budget_remaining": dict(view.get("budget_remaining") or {}), "history": []}
    )
    if not guard["ok"]:
        raise LegionError(f"over budget: {guard['reason']}")
    safe = {key: value for key, value in kwargs.items() if key not in _STRIP}
    produced = fn(view, **safe)
    if not isinstance(produced, dict):
        produced = {"result": produced}
    result = dict(produced)
    result["risk"] = risk
    result["verified"] = False
    result["gated_write"] = False
    result["kin"] = kin
    result["temporary"] = True
    host = packet if isinstance(packet, dict) else view
    evidence_attach(
        {"tool": name, "risk_class": risk["risk_class"], "verified": False},
        f"legion:{kin}:{name}",
        host,
    )
    return result


def _bind(parent: str, name: str, attempt_id: str, fn: Callable[..., Any] | None) -> Callable[..., Any]:
    def call(packet: Any, **kwargs: Any) -> dict[str, Any]:
        if attempt_id not in _ATTEMPTS:
            raise DemigodError("demigod swarm is not mounted")
        if fn is None:
            produced = invoke_legion(parent, name, packet, **kwargs)
        else:
            produced = _gated_helper(parent, name, fn, packet, **kwargs)
        note_worker(attempt_id, name, produced)
        return produced

    call.__name__ = name
    return call


def prepare_swarm(
    demigod: str,
    packet: Any,
    swarm: list[str] | None,
    *,
    guide_names: set[str],
) -> list[str]:
    """Validate swarm names. Does not mount them."""
    if not swarm:
        return []
    if not isinstance(swarm, (list, tuple)):
        raise DemigodError("swarm must be a list of legion names")
    parent = PARENT_KIN.get(demigod)
    if parent is None:
        raise DemigodError(f"no parent kin for {demigod}")
    current = swarm_meta(packet)
    if current and current.get("demigod") != demigod:
        raise DemigodError("a demigod swarm is already mounted")
    catalogue = {row["name"] for row in kin_catalogue(parent)}
    helpers = CHECK_LOCAL.get(demigod, {})
    names: list[str] = []
    for raw in swarm:
        if not isinstance(raw, str) or _NAME.fullmatch(raw) is None:
            raise DemigodError(f"rejected swarm name: {raw!r}")
        if raw in guide_names:
            raise DemigodHierarchyError("a demigod cannot summon another demigod")
        if raw in names:
            continue
        if raw in catalogue or raw in helpers:
            names.append(raw)
            continue
        raise DemigodError(f"swarm legion {raw} is not on {parent}")
    return names


def commit_swarm(demigod: str, packet: Any, names: list[str]) -> dict[str, Any]:
    """Mount an already validated name list onto this attempt."""
    if not names:
        return {"attempt_id": None, "names": []}
    parent = PARENT_KIN[demigod]
    current = swarm_meta(packet)
    if current and current.get("demigod") == demigod:
        drop_swarm(packet, demigod=demigod)
    attempt_id = f"{_packet_id(packet)}:{demigod}:{uuid.uuid4().hex[:8]}"
    helpers = CHECK_LOCAL.get(demigod, {})
    surface: dict[str, Callable[..., Any]] = {}
    spawners: list[str] = []
    for name in names:
        if name in helpers:
            surface[name] = _bind(parent, name, attempt_id, helpers[name])
        else:
            surface[name] = _bind(parent, name, attempt_id, None)
            if legion_spawns(parent, name):
                spawners.append(name)
    meta = {
        "attempt_id": attempt_id,
        "demigod": demigod,
        "parent_kin": parent,
        "names": list(surface),
    }
    _ATTEMPTS[attempt_id] = _Attempt(
        attempt_id=attempt_id,
        demigod=demigod,
        parent_kin=parent,
        names=list(surface),
        surface=surface,
    )
    _set_swarm(packet, meta)
    try:
        for name in spawners:
            reserve_spawner(attempt_id, name)
    except Exception:
        drop_swarm(packet, demigod=demigod)
        raise
    return meta


def swarm_surface(packet: Any) -> dict[str, Callable[..., Any]]:
    meta = swarm_meta(packet)
    if meta is None:
        return {}
    attempt = _ATTEMPTS.get(str(meta.get("attempt_id")))
    if attempt is None:
        raise DemigodError("demigod swarm is not mounted")
    return dict(attempt.surface)


def drop_swarm(packet: Any, *, demigod: str | None = None) -> dict[str, Any] | None:
    """Drop the temporary surface and stop its process group."""
    meta = swarm_meta(packet)
    if meta is None:
        return None
    if demigod is not None and meta.get("demigod") != demigod:
        return None
    _pop_swarm(packet)
    attempt_id = str(meta.get("attempt_id") or "")
    _ATTEMPTS.pop(attempt_id, None)
    if not attempt_id:
        return None
    report = stop_owner(attempt_id)
    report["attempt_id"] = attempt_id
    return report


def demigod_stop(packet: Any) -> dict[str, Any]:
    """Ask Atropos to cut the attempt group. The guide stays until dismiss."""
    meta = swarm_meta(packet)
    if meta is None:
        return {
            "state": "running",
            "stop_requested": False,
            "fully_stopped": False,
            "owned": 0,
            "handles": [],
        }
    report = stop_owner(str(meta.get("attempt_id") or ""))
    report["attempt_id"] = meta.get("attempt_id")
    return report


@contextmanager
def demigod_attempt(
    name: str,
    packet: Any,
    swarm: list[str] | None = None,
) -> Iterator[dict[str, Callable[..., Any]]]:
    """Summon, yield the temporary surface, and dismiss when the check returns."""
    from resileos.kin.demigods.router import demigod_dismiss, demigod_summon

    demigod_summon(name, packet, swarm=swarm)
    try:
        yield swarm_surface(packet)
    finally:
        demigod_dismiss(name, packet)
