"""Bounded operational state for the auto upgrade tier.

This store holds only tool-selection weights, search and crawl cache
entries, source-quality ranks, and metric thresholds or tuning
parameters. Values must stay inside the declared bounds. A change is
versioned, gated on a named metric, and auto-reverted if that metric
gets worse, or if any L0 or L1 coherence metric on the held-out suite
gets worse (``guard_before`` at apply, ``guard_after`` at evaluate).
These targets are the L2 params of the harness level registry in
``upgrade_report.LEVELS``; nothing at L0 or L1 lives here. Every apply and revert is logged on an upgrade report.

This store never writes code or config files, never calls Eat or
learn, never touches the scar matrix or Titanos, and never flips
``require_verified`` or the Metis mouth defaults.

Search and crawl caches here are a tuning interface. Hermes envelopes
do not read them yet; hookup is documented in
``docs/320-titanos/upgrade-proposals.md``.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

# Explicit auto allowlist: L2 params only. Anything else defaults to review.
AUTO_TARGETS = frozenset(
    {
        "tool_weights",
        "tool_preferences",
        "search_cache",
        "crawl_cache",
        "source_quality_ranking",
        "metric_thresholds",
        "tuning_params",
    }
)

# Declared bounds. Auto-apply is refused outside them.
BOUNDS: dict[str, dict[str, float]] = {
    "tool_weights": {"min": 0.0, "max": 1.0},
    "tool_preferences": {"min": 0.0, "max": 1.0},
    "source_quality_ranking": {"min": 0.0, "max": 1.0},
    "metric_thresholds": {"min": 0.0, "max": 1.0},
    "tuning_params": {"min": -8.0, "max": 8.0},
    "search_cache": {"max_entries": 256, "max_value_bytes": 4096},
    "crawl_cache": {"max_entries": 256, "max_value_bytes": 4096},
}

_CACHE_TARGETS = frozenset({"search_cache", "crawl_cache"})
_NUMERIC_TARGETS = AUTO_TARGETS - _CACHE_TARGETS


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def in_bounds(target: str, value: Any) -> bool:
    """True when ``value`` is legal for an auto-tier target."""
    if target not in AUTO_TARGETS:
        return False
    limits = BOUNDS[target]
    if target in _CACHE_TARGETS:
        if not isinstance(value, dict):
            return False
        if len(value) > int(limits["max_entries"]):
            return False
        for key, item in value.items():
            raw = item if isinstance(item, (bytes, bytearray)) else str(item).encode("utf-8")
            if len(str(key)) + len(raw) > int(limits["max_value_bytes"]):
                return False
        return True
    if isinstance(value, dict):
        return all(in_bounds(target, item) for item in value.values())
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return float(limits["min"]) <= number <= float(limits["max"])


def _numbers(metrics: dict[str, Any] | None) -> dict[str, float]:
    """Keep only the numeric metrics of a held-out result (drops labels, counts)."""
    return {k: float(v) for k, v in (metrics or {}).items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)}


class OperationalStore:
    """Versioned, metric-gated operational state. Not a code or config editor."""

    def __init__(self) -> None:
        self.state: dict[str, Any] = {name: {} for name in AUTO_TARGETS}
        self.version = 0
        self.history: list[dict[str, Any]] = []
        self._pending: dict[int, dict[str, Any]] = {}

    def snapshot(self) -> dict[str, Any]:
        return {"version": self.version, "state": deepcopy(self.state)}

    def apply(
        self,
        *,
        target: str,
        key: str,
        value: Any,
        metric_name: str,
        metric_before: float,
        report: Any | None = None,
        guard_before: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Apply one in-bounds auto change and record a version.

        The change stays pending evaluation until ``evaluate`` sees a
        later metric. Worse metrics revert this version.
        """
        if target not in AUTO_TARGETS:
            return {
                "ok": False,
                "applied": False,
                "reason": "target is not on the auto allowlist",
                "target": target,
            }
        check = value if target in _CACHE_TARGETS else {key: value}
        if not in_bounds(target, check):
            return {
                "ok": False,
                "applied": False,
                "reason": "value is outside declared bounds",
                "target": target,
                "key": key,
            }
        before = self.snapshot()
        bucket = self.state.setdefault(target, {})
        previous = deepcopy(bucket.get(key))
        bucket[key] = deepcopy(value)
        self.version += 1
        record = {
            "version": self.version,
            "target": target,
            "key": key,
            "value": deepcopy(value),
            "previous": previous,
            "metric_name": str(metric_name),
            "metric_before": float(metric_before),
            "applied_at": _now(),
            "status": "applied_pending_metric",
            "reverted": False,
            "guard_before": _numbers(guard_before),
        }
        self.history.append(record)
        self._pending[self.version] = {"previous": previous, "before": before, **record}
        if report is not None:
            report.log_auto(record)
        return {"ok": True, "applied": True, "version": self.version, "record": record}

    def evaluate(
        self,
        version: int,
        metric_after: float,
        *,
        report: Any | None = None,
        guard_after: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Keep the change only if nothing it guards got worse.

        Reverts when the gated metric dropped, or when any L0/L1
        coherence metric recorded in ``guard_before`` is lower in
        ``guard_after`` (a missing after-value counts as worse).
        """
        pending = self._pending.get(int(version))
        if pending is None:
            return {"ok": False, "reason": "no pending change at that version"}
        before = float(pending["metric_before"])
        after = float(metric_after)
        record = dict(pending)
        record["metric_after"] = after
        guard_before = pending.get("guard_before") or {}
        degraded = []
        if guard_before:
            from resileos.persona.upgrade_report import guard_l2

            check = guard_l2(guard_before, guard_after or {})
            degraded = check["degraded"]
            record["guard_after"] = _numbers(guard_after)
            record["degraded"] = degraded
        if after < before or degraded:
            target = pending["target"]
            key = pending["key"]
            self.state.setdefault(target, {})
            previous = pending["previous"]
            if previous is None:
                self.state[target].pop(key, None)
            else:
                self.state[target][key] = deepcopy(previous)
            self.version += 1
            record["status"] = "reverted"
            record["reverted"] = True
            record["reverted_to"] = pending["before"]["version"]
            record["reverted_at"] = _now()
            record["revert_version"] = self.version
        else:
            record["status"] = "kept"
            record["reverted"] = False
        self.history.append({k: record[k] for k in record if k != "before"})
        self._pending.pop(int(version), None)
        if report is not None:
            report.log_auto(record)
        return {"ok": True, **{k: record[k] for k in record if k != "before"}}
