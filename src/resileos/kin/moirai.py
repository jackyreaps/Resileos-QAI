"""Clotho, Lachesis, Atropos, and Harmonia under Hermes.

Classical hash and field overlap. Shared work is kept only after residual
consistency and verify_on_stop. Stop ends owned process groups, not a flag alone.
"""
from __future__ import annotations

import os
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from resileos.harness.tools import verify_on_stop

OVERLAP_THRESHOLD = 0.8
_PREFIX_FIELDS = ("id", "subject", "relation", "artefact", "lesson")


@dataclass
class Thread:
    handle_id: str
    owner: str
    pgid: Optional[int] = None
    cancel: Optional[Callable[[], None]] = None
    parent_id: Optional[str] = None
    manual_exit: bool = False
    stop_requested: bool = False
    exited: bool = False


def _prefix_values(packet: Any) -> list[str]:
    if packet is None:
        return []
    if hasattr(packet, "to_dict"):
        data = packet.to_dict()
    elif isinstance(packet, dict):
        data = packet
    else:
        return []
    return [str(data[key]) for key in _PREFIX_FIELDS if key in data and data[key] is not None]


def hash_prefix_ratio(left: str, right: str) -> float:
    a = str(left or "")
    b = str(right or "")
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    shared = 0
    for one, two in zip(a, b):
        if one != two:
            break
        shared += 1
    return shared / max(len(a), len(b))


def packet_prefix_ratio(left: Any, right: Any) -> float:
    a = _prefix_values(left)
    b = _prefix_values(right)
    if not a or not b:
        return 0.0
    shared = 0
    for one, two in zip(a, b):
        if one != two:
            break
        shared += 1
    return shared / max(len(a), len(b))


def overlap_score(hash_a: str, hash_b: str, packet_a: Any, packet_b: Any) -> float:
    return max(hash_prefix_ratio(hash_a, hash_b), packet_prefix_ratio(packet_a, packet_b))


def _live_group_pids(pgid: int) -> list[int]:
    """Pids still running in this process group. Zombies do not count."""
    live: list[int] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            raw = (entry / "stat").read_text(encoding="utf-8")
        except OSError:
            continue
        end = raw.rfind(")")
        if end < 0:
            continue
        fields = raw[end + 2 :].split()
        if len(fields) < 3:
            continue
        try:
            pgrp = int(fields[2])
        except ValueError:
            continue
        if pgrp == pgid and fields[0] != "Z":
            live.append(int(entry.name))
    return live


def _kill_group(pgid: int) -> bool:
    """Terminate a process group. True when no live member remains.

    Refuses the current process group so a stop cannot take down the caller.
    """
    if pgid <= 1 or pgid == os.getpgrp():
        return False
    deadline = time.monotonic() + 0.6
    sent_kill = False
    while time.monotonic() < deadline:
        if not _live_group_pids(pgid):
            return True
        try:
            os.killpg(pgid, signal.SIGKILL if sent_kill else signal.SIGTERM)
        except ProcessLookupError:
            return True
        except (PermissionError, OSError):
            return False
        sent_kill = True
        time.sleep(0.02)
    return not _live_group_pids(pgid)


@dataclass
class Clotho:
    """Register process-group or cancel-token ownership for Hermes work."""

    threads: dict[str, Thread] = field(default_factory=dict)

    def spin(
        self,
        owner: str,
        *,
        handle_id: str,
        pgid: Optional[int] = None,
        cancel: Optional[Callable[[], None]] = None,
        parent_id: Optional[str] = None,
        manual_exit: bool = False,
    ) -> Thread:
        if parent_id is not None and parent_id not in self.threads:
            raise KeyError(f"unknown parent thread: {parent_id}")
        thread = Thread(
            handle_id=handle_id,
            owner=owner,
            pgid=pgid,
            cancel=cancel,
            parent_id=parent_id,
            manual_exit=manual_exit,
        )
        self.threads[handle_id] = thread
        return thread

    def owned(self, owner: str) -> list[Thread]:
        return [thread for thread in self.threads.values() if thread.owner == owner]


@dataclass
class Lachesis:
    """Cost-gated fan-out. Expand only when expected gain exceeds cost."""

    active: dict[str, dict[str, Any]] = field(default_factory=dict)

    def note(self, cycle_id: str, packet: Any, residual_hash: str) -> None:
        self.active[cycle_id] = {
            "packet": packet,
            "residual_hash": str(residual_hash or ""),
        }

    def measure(self, *, expected_gain: float, budget_cost: float) -> dict[str, Any]:
        gain = float(expected_gain)
        cost = float(budget_cost)
        expand = gain > cost
        return {
            "expand": expand,
            "expected_gain": gain,
            "budget_cost": cost,
            "reason": "gain_exceeds_cost" if expand else "gain_does_not_exceed_cost",
        }


@dataclass
class Atropos:
    """Session interrupt plus process-group termination."""

    clotho: Clotho
    stops: dict[str, str] = field(default_factory=dict)

    def state(self, owner: str) -> str:
        if self.stops.get(owner) != "cut":
            return "running"
        threads = self.clotho.owned(owner)
        if threads and all(thread.exited for thread in threads):
            return "fully_stopped"
        if not threads:
            return "fully_stopped"
        return "stop_requested"

    def cut(self, owner: str) -> dict[str, Any]:
        self.stops[owner] = "cut"
        threads = self.clotho.owned(owner)
        for thread in threads:
            thread.stop_requested = True
            if thread.cancel is not None:
                thread.cancel()
            if thread.pgid is not None:
                thread.exited = _kill_group(thread.pgid)
            elif thread.manual_exit:
                thread.exited = False
            else:
                thread.exited = True
        status = self.state(owner)
        return {
            "state": status,
            "stop_requested": status != "running",
            "fully_stopped": status == "fully_stopped",
            "owned": len(threads),
        }

    def confirm_exit(self, handle_id: str) -> str:
        thread = self.clotho.threads[handle_id]
        thread.exited = True
        return self.state(thread.owner)

    def on_stop(self, owner: str, callback: Callable[[], None]) -> str:
        """Hook for a legion that holds files, subprocesses, or sessions."""
        handle_id = f"{owner}:hook:{len(self.clotho.threads)}"
        self.clotho.spin(owner, handle_id=handle_id, cancel=callback)
        return handle_id


@dataclass
class Harmonia:
    """Share a residual or draft step when hash or packet prefix overlap is high."""

    lachesis: Lachesis
    threshold: float = OVERLAP_THRESHOLD

    def similarity(self, hash_a: str, hash_b: str, packet_a: Any, packet_b: Any) -> float:
        return overlap_score(hash_a, hash_b, packet_a, packet_b)

    def route(self, cycle_id: str, residual_hash: str, packet: Any) -> dict[str, Any]:
        best_id = None
        best_score = 0.0
        for other_id, other in self.lachesis.active.items():
            if other_id == cycle_id:
                continue
            score = self.similarity(
                residual_hash,
                other.get("residual_hash") or "",
                packet,
                other.get("packet"),
            )
            if score > best_score:
                best_score = score
                best_id = other_id
        self.lachesis.note(cycle_id, packet, residual_hash)
        if best_id is not None and best_score >= self.threshold:
            return {
                "path": "shared",
                "shared_with": best_id,
                "score": best_score,
                "shared_step": "residual",
            }
        return {"path": "independent", "shared_with": None, "score": best_score}

    def certify(
        self,
        *,
        residual_consistent: bool,
        apollo_result: Optional[dict] = None,
        packet: Optional[dict] = None,
    ) -> dict[str, Any]:
        verdict = verify_on_stop(dict(packet or {}), apollo_result)
        accepted = bool(residual_consistent) and bool(verdict.get("verified"))
        return {
            "accepted": accepted,
            "certified_leaf": accepted,
            "verify_on_stop": verdict,
            "residual_consistent": bool(residual_consistent),
        }


@dataclass
class HermesCoordination:
    clotho: Clotho = field(default_factory=Clotho)
    lachesis: Lachesis = field(default_factory=Lachesis)
    atropos: Atropos = field(init=False)
    harmonia: Harmonia = field(init=False)

    def __post_init__(self) -> None:
        self.atropos = Atropos(self.clotho)
        self.harmonia = Harmonia(self.lachesis)


_DESK: HermesCoordination | None = None


def get_coordination() -> HermesCoordination:
    global _DESK
    if _DESK is None:
        _DESK = HermesCoordination()
    return _DESK


def reset_coordination() -> HermesCoordination:
    global _DESK
    _DESK = HermesCoordination()
    return _DESK


def cut_owned(owner: str, *, reason: str = "") -> dict[str, Any]:
    desk = get_coordination()
    if not desk.clotho.owned(owner):
        return {"state": "running", "owned": 0, "stop_requested": False, "reason": reason}
    out = desk.atropos.cut(owner)
    out["reason"] = reason
    return out


def checkpoint_allowed(owner: str, *, residual_consistent: bool) -> tuple[bool, str]:
    """Hades may record after a stop only once the group is dead and consistency holds."""
    if not residual_consistent:
        return False, "residual consistency does not hold"
    status = get_coordination().atropos.state(owner)
    if status == "stop_requested":
        return False, "stop requested"
    if status == "fully_stopped":
        return True, "fully stopped"
    return True, "no stop requested"


__all__ = [
    "OVERLAP_THRESHOLD",
    "Atropos",
    "Clotho",
    "Harmonia",
    "HermesCoordination",
    "Lachesis",
    "Thread",
    "checkpoint_allowed",
    "cut_owned",
    "get_coordination",
    "hash_prefix_ratio",
    "overlap_score",
    "packet_prefix_ratio",
    "reset_coordination",
]
