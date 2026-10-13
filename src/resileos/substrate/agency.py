"""
Hierarchical routing layer.

STATUS: heuristic. Not a formal extension of the substrate. No theorem
in this repository or in the external OscGraph package establishes
that a child with mean CSI below a threshold *should* be deactivated.
The thresholds are chosen operational parameters. See RES-307 §0.

Children are specialized query handlers. The group maintains a weight
per child and routes each query to the highest-weight active child.
After each query the selected child receives a fitness update. A child
whose fitness falls below both thresholds is "eaten" — removed from the
routing pool. Weight is not transferred to another child. The parent
simply stops offering queries to it.

No state is written to the frozen residual core. The parent's memory
layer is the only mutable state that survives a query.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np


# A handler is `callable(parent, subject, relation, inverse) -> Answer | None`.
# The Answer type is defined by the consuming module. Returning None means
# "this child declines"; the caller may fall through to a parent path.
HandlerFn = Callable[[Any, str, str, bool], Any]


@dataclass
class AgencyChild:
    """
    A specialized query handler with a hierarchy weight.

    Fields:
        name            unique identifier
        handler         callable (parent, subject, relation, inverse) -> Answer|None
        weight          routing weight; higher = more likely selected
        active          False once eaten; excluded from selection
        local_csi       rolling window of CSI values from this child's queries
        contribution    EMA of 1.0 for accepted answers, 0.0 for abstained
        query_count     total queries routed to this child
        accept_count    queries that returned a non-abstaining answer
        csi_window      size of the rolling CSI window
    """

    name: str
    handler: HandlerFn
    weight: float = 1.0
    active: bool = True
    local_csi: list[float] = field(default_factory=list)
    contribution: float = 0.0
    query_count: int = 0
    accept_count: int = 0
    csi_window: int = 32

    def update_fitness(self, csi: float, contribution: float) -> None:
        self.local_csi.append(float(csi))
        if len(self.local_csi) > self.csi_window:
            self.local_csi.pop(0)
        # EMA on contribution with slow decay.
        self.contribution = 0.9 * self.contribution + 0.1 * float(contribution)

    @property
    def mean_csi(self) -> float:
        return float(np.mean(self.local_csi)) if self.local_csi else 1.0

    @property
    def accept_rate(self) -> float:
        if self.query_count == 0:
            return 0.0
        return self.accept_count / self.query_count


class AgencyGroup:
    """
    Routes queries to children by weight. Eats children whose fitness
    is poor. STATUS: heuristic.

    Parameters:
        eat_threshold_csi        mean CSI below this makes a child edible
        eat_threshold_contrib    EMA contribution below this too
        min_queries_before_eat   require this many queries before eating
                                 (avoids noisy early decisions)
        min_weight               below this, a child is fully deactivated
        absorption_rate          weight multiplier applied at each eat step
    """

    def __init__(self,
                 eat_threshold_csi: float = 0.35,
                 eat_threshold_contrib: float = 0.15,
                 min_queries_before_eat: int = 10,
                 min_weight: float = 0.05,
                 absorption_rate: float = 0.4):
        if not (0.0 <= absorption_rate < 1.0):
            raise ValueError("absorption_rate must be in [0, 1)")
        if min_weight < 0.0:
            raise ValueError("min_weight must be ≥ 0")
        self.children: dict[str, AgencyChild] = {}
        self.eat_threshold_csi = float(eat_threshold_csi)
        self.eat_threshold_contrib = float(eat_threshold_contrib)
        self.min_queries_before_eat = int(min_queries_before_eat)
        self.min_weight = float(min_weight)
        self.absorption_rate = float(absorption_rate)
        self.eaten: list[str] = []

    # ── registration ─────────────────────────────────────────────────
    def add_child(self, name: str, handler: HandlerFn,
                  weight: float = 1.0) -> AgencyChild:
        if name in self.children:
            raise ValueError(f"child {name!r} already registered")
        if weight <= 0.0:
            raise ValueError("weight must be > 0")
        child = AgencyChild(name=name, handler=handler, weight=float(weight))
        self.children[name] = child
        self._normalize_weights()
        return child

    def remove_child(self, name: str) -> None:
        self.children.pop(name, None)
        self._normalize_weights()

    # ── selection ────────────────────────────────────────────────────
    def select(self) -> AgencyChild | None:
        """
        Return the active child with the highest weight, or None if no
        children are registered or all have been eaten. Deterministic.
        """
        active = [c for c in self.children.values() if c.active]
        if not active:
            return None
        return max(active, key=lambda c: c.weight)

    def _normalize_weights(self) -> None:
        total = sum(c.weight for c in self.children.values() if c.active)
        if total <= 0.0:
            return
        for c in self.children.values():
            if c.active:
                c.weight = c.weight / total

    # ── fitness updates ──────────────────────────────────────────────
    def record(self, name: str, csi: float, accepted: bool) -> None:
        child = self.children.get(name)
        if child is None or not child.active:
            return
        child.query_count += 1
        if accepted:
            child.accept_count += 1
        child.update_fitness(csi, contribution=1.0 if accepted else 0.0)

    # ── eating ───────────────────────────────────────────────────────
    def eat(self, name: str) -> bool:
        """
        Attempt to eat a child. Returns True if the child was affected
        (weight reduced). A child is fully deactivated when its weight
        drops below min_weight after eating. A child is only edible when:
            - query_count >= min_queries_before_eat
            - mean_csi < eat_threshold_csi
            - contribution < eat_threshold_contrib
        """
        child = self.children.get(name)
        if child is None or not child.active:
            return False
        if child.query_count < self.min_queries_before_eat:
            return False
        if child.mean_csi >= self.eat_threshold_csi:
            return False
        if child.contribution >= self.eat_threshold_contrib:
            return False

        child.weight *= (1.0 - self.absorption_rate)
        if child.weight < self.min_weight:
            child.active = False
            if name not in self.eaten:
                self.eaten.append(name)
        self._normalize_weights()
        return True

    def evaluate_and_prune(self) -> list[str]:
        """
        Attempt to eat every active child. Return the names of children
        that transitioned to inactive during this call.
        """
        newly_inactive: list[str] = []
        for name in list(self.children.keys()):
            child = self.children[name]
            was_active = child.active
            self.eat(name)
            if was_active and not child.active:
                newly_inactive.append(name)
        return newly_inactive

    # ── introspection ────────────────────────────────────────────────
    def snapshot(self) -> dict:
        return {
            "children": {
                name: {
                    "weight": float(c.weight),
                    "active": bool(c.active),
                    "query_count": int(c.query_count),
                    "accept_count": int(c.accept_count),
                    "accept_rate": float(c.accept_rate),
                    "mean_csi": float(c.mean_csi),
                    "contribution": float(c.contribution),
                }
                for name, c in self.children.items()
            },
            "eaten": list(self.eaten),
        }


__all__ = ["AgencyChild", "AgencyGroup", "HandlerFn"]
