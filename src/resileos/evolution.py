"""
Outer-loop substrate evolution.

Evolves the substrate's *configuration* — rank, loop count, feature
mask — by measuring carrier val loss for each candidate. Never touches
the residual algebra: each candidate instantiates a fresh ResidualCore
with the given config, the substrate emits frozen features, the carrier
is trained on a training split, and the reward is measured on a held-out
val split.

Gradient flow:

    downstream loss
      -> carrier MLP parameters         (trained per candidate)
      -> feature pack (NumPy, frozen)
      -> substrate internals (frozen, never in autograd)

The substrate's contract (RES-200, RES-201, RES-401) is preserved for
every candidate. What changes across candidates is r, n_loops, and which
monitors reach the carrier.

Search strategies:

    grid    exhaustive over a discrete grid (small spaces only)
    random  uniform sampling with a fixed budget

The loop is deterministic given (search_space, strategy, seed).
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Iterable, Iterator, Optional

import numpy as np


# ── evolvable config ────────────────────────────────────────────────────
@dataclass(frozen=True)
class SubstrateConfig:
    """
    Substrate configuration that the outer loop can vary.

    r           scar rank.                  bounded by min(m, n)
    n_loops     recurrent refinement steps. affects CSI, R, and scar drift
    feature_mask subset of feature names to include. The full set is
                ('packet', 'csi', 'order_parameter', 'direction')
                'packet' is always available; the rest are optional.

    The config is frozen (immutable). Different candidates are distinct
    instances. This is deliberate: nothing mutates in place.
    """
    r: int = 8
    n_loops: int = 12
    feature_mask: tuple[str, ...] = ("packet",)

    def __post_init__(self) -> None:
        if self.r < 1:
            raise ValueError("r must be >= 1")
        if self.n_loops < 1:
            raise ValueError("n_loops must be >= 1")
        allowed = {"packet", "csi", "order_parameter", "direction"}
        unknown = set(self.feature_mask) - allowed
        if unknown:
            raise ValueError(f"unknown feature names: {unknown}")
        if "packet" not in self.feature_mask:
            raise ValueError("'packet' must always be in feature_mask")


@dataclass
class EvolutionRecord:
    config: SubstrateConfig
    reward: float                    # lower is better (val loss)
    metadata: dict[str, Any] = field(default_factory=dict)


# ── search strategies ───────────────────────────────────────────────────
def _grid_candidates(
    r_values: Iterable[int],
    n_loops_values: Iterable[int],
    feature_masks: Iterable[tuple[str, ...]],
) -> list[SubstrateConfig]:
    return [
        SubstrateConfig(r=r, n_loops=n, feature_mask=tuple(mask))
        for r, n, mask in itertools.product(
            sorted(set(r_values)),
            sorted(set(n_loops_values)),
            [tuple(m) for m in feature_masks],
        )
    ]


def _random_candidates(
    r_values: list[int],
    n_loops_values: list[int],
    feature_masks: list[tuple[str, ...]],
    budget: int,
    seed: int,
) -> list[SubstrateConfig]:
    rng = np.random.default_rng(seed)
    out: list[SubstrateConfig] = []
    seen: set[SubstrateConfig] = set()
    guard = 0
    while len(out) < budget and guard < budget * 100:
        r = int(rng.choice(r_values))
        n = int(rng.choice(n_loops_values))
        mask_idx = int(rng.integers(0, len(feature_masks)))
        cfg = SubstrateConfig(r=r, n_loops=n, feature_mask=feature_masks[mask_idx])
        if cfg not in seen:
            seen.add(cfg)
            out.append(cfg)
        guard += 1
    return out


# ── loop ────────────────────────────────────────────────────────────────
class EvolutionLoop:
    """
    Propose a config, evaluate it (caller supplies the evaluator),
    record the reward, repeat.

    Parameters
    ----------
    r_values, n_loops_values : iterable of int
        Grid values for the corresponding fields.
    feature_masks : iterable of tuples
        Candidate feature masks. Each must include 'packet'.
    strategy : 'grid' | 'random'
    budget : int
        Max number of evaluations. For grid, budget is ignored and the
        full grid is used (capped to len(grid)).
    seed : int
        Reproducibility for the random strategy.
    """

    def __init__(
        self,
        r_values: Iterable[int] = (4, 6, 8, 12),
        n_loops_values: Iterable[int] = (4, 8, 12),
        feature_masks: Iterable[tuple[str, ...]] = (
            ("packet",),
            ("packet", "csi"),
            ("packet", "csi", "order_parameter"),
            ("packet", "csi", "order_parameter", "direction"),
        ),
        strategy: str = "grid",
        budget: int = 32,
        seed: int = 0,
    ) -> None:
        if strategy not in ("grid", "random"):
            raise ValueError(f"strategy: {strategy!r}")
        r_list = sorted(set(int(x) for x in r_values))
        n_list = sorted(set(int(x) for x in n_loops_values))
        mask_list = [tuple(m) for m in feature_masks]
        # Validate every mask up front.
        for m in mask_list:
            SubstrateConfig(r=r_list[0], n_loops=n_list[0], feature_mask=m)

        self.r_values = r_list
        self.n_loops_values = n_list
        self.feature_masks = mask_list
        self.strategy = strategy
        self.budget = int(budget)
        self.seed = int(seed)

        if strategy == "grid":
            self._candidates = _grid_candidates(r_list, n_list, mask_list)[: self.budget]
        else:
            self._candidates = _random_candidates(
                r_list, n_list, mask_list, self.budget, self.seed
            )

        self._index = 0
        self._history: list[EvolutionRecord] = []

    # ── proposal / observation ────────────────────────────────────────
    def __iter__(self) -> Iterator[SubstrateConfig]:
        return iter(self._candidates)

    def __len__(self) -> int:
        return len(self._candidates)

    def observe(self, config: SubstrateConfig, reward: float,
                **metadata: Any) -> None:
        self._history.append(
            EvolutionRecord(config=config, reward=float(reward),
                            metadata=dict(metadata))
        )

    def run(self, evaluate: Callable[[SubstrateConfig], float],
            **kwargs: Any) -> "EvolutionLoop":
        """
        Iterate all candidates, calling evaluate(config) -> reward.
        Reward is lower-is-better.

        kwargs are forwarded to observe() as metadata.
        """
        for cfg in self._candidates:
            reward = float(evaluate(cfg))
            self.observe(cfg, reward, **kwargs)
        return self

    # ── introspection ─────────────────────────────────────────────────
    def history(self) -> list[EvolutionRecord]:
        return list(self._history)

    def best(self) -> Optional[EvolutionRecord]:
        if not self._history:
            return None
        return min(self._history, key=lambda r: r.reward)

    def ranked(self) -> list[EvolutionRecord]:
        return sorted(self._history, key=lambda r: r.reward)

    def summary(self) -> dict:
        if not self._history:
            return {"n": 0}
        rewards = np.array([r.reward for r in self._history], dtype=np.float64)
        best = self.best()
        return {
            "n_evaluated": len(self._history),
            "reward_min": float(rewards.min()),
            "reward_max": float(rewards.max()),
            "reward_mean": float(rewards.mean()),
            "reward_std": float(rewards.std()),
            "best_config": {
                "r": best.config.r,
                "n_loops": best.config.n_loops,
                "feature_mask": list(best.config.feature_mask),
            },
            "best_reward": float(best.reward),
        }


__all__ = ["SubstrateConfig", "EvolutionRecord", "EvolutionLoop"]
