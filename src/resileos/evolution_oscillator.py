"""
Oscillator-oriented discrete grid search.

Wraps the same grid as EvolutionLoop. Uses a KuramotoField to bias
the order in which grid candidates are proposed.

Orientation:
    - Three oscillators, one per optional mask bit
      (csi, order_parameter, direction).
    - dtheta_i < 0  -> prefer flipping mask bit i.
    - dtheta_i >= 0 -> prefer keeping mask bit i.

Level:
    - R sets the target distance from the current best config.
    - R = 1 (locked)   -> propose near the best.
    - R = 0 (exploring) -> propose far from the best.

Coupling drive (epsilon_source):
    - "best_reward" (default): epsilon = best reward so far.
    - "monitors": epsilon = epsilon_from_monitors(bundle of current best).
      Requires the evaluator to return (reward, MonitorBundle).
      If a bundle is not available, falls back to best_reward.

Discrete grid only. Deterministic given (grid, field config, seed).
"""
from __future__ import annotations

from typing import Any, Callable, Iterable, Optional, Union

import numpy as np

from .evolution import SubstrateConfig, EvolutionRecord
from .monitors import MonitorBundle, epsilon_from_monitors
from .substrate.oscillator import KuramotoField


MASK_BITS = ("csi", "order_parameter", "direction")

# Evaluator may return a float, or (float, MonitorBundle).
EvalReturn = Union[float, tuple[float, MonitorBundle]]
Evaluator = Callable[[SubstrateConfig], EvalReturn]


def _all_grid_candidates(r_values, n_loops_values, feature_masks):
    return [
        SubstrateConfig(r=r, n_loops=n, feature_mask=tuple(m))
        for r in r_values
        for n in n_loops_values
        for m in feature_masks
    ]


class OscillatorOrientedSearch:

    def __init__(
        self,
        r_values: Iterable[int] = (4, 6, 8, 12),
        n_loops_values: Iterable[int] = (4, 8, 12),
        feature_masks: Iterable[tuple] = (
            ("packet",),
            ("packet", "csi"),
            ("packet", "csi", "order_parameter"),
            ("packet", "csi", "order_parameter", "direction"),
        ),
        field: Optional[KuramotoField] = None,
        budget: int = 36,
        seed: int = 0,
        kappa: float = 1.0,
        omega_base: float = 2.0 * np.pi,
        dt: float = 0.1,
        mask_weight: float = 0.6,
        r_weight: float = 0.3,
        n_loops_weight: float = 0.1,
        theta_flip_penalty: float = 0.1,
        epsilon_source: str = "best_reward",
    ) -> None:
        if epsilon_source not in ("best_reward", "monitors"):
            raise ValueError(f"epsilon_source: {epsilon_source!r}")

        self.r_values = sorted(set(int(x) for x in r_values))
        self.n_loops_values = sorted(set(int(x) for x in n_loops_values))
        self.feature_masks = [tuple(m) for m in feature_masks]
        if not self.r_values or not self.n_loops_values or not self.feature_masks:
            raise ValueError("empty search space")
        for m in self.feature_masks:
            SubstrateConfig(r=self.r_values[0],
                            n_loops=self.n_loops_values[0],
                            feature_mask=m)

        self.budget = int(budget)
        self.seed = int(seed)
        self.epsilon_source = epsilon_source

        if field is None:
            field = KuramotoField(
                r=len(MASK_BITS),
                ladder="golden_powers",
                omega_base=float(omega_base),
                kappa=float(kappa),
                alpha=0.5,
                dt=float(dt),
                random_start=True,
                seed=seed,
            )
        if field.r != len(MASK_BITS):
            raise ValueError(
                f"field must have {len(MASK_BITS)} oscillators, got {field.r}")
        self.field = field
        self.W = np.ones((len(MASK_BITS), len(MASK_BITS))) - np.eye(len(MASK_BITS))

        total = mask_weight + r_weight + n_loops_weight
        if total <= 0.0:
            raise ValueError("score weights must not all be zero")
        self.w_mask = float(mask_weight) / total
        self.w_r = float(r_weight) / total
        self.w_nl = float(n_loops_weight) / total
        self.theta_flip_penalty = float(theta_flip_penalty)

        self._grid = _all_grid_candidates(
            self.r_values, self.n_loops_values, self.feature_masks)
        self._visited: set[SubstrateConfig] = set()
        self._history: list[EvolutionRecord] = []
        self._center: Optional[SubstrateConfig] = None
        self._bundles: dict[SubstrateConfig, MonitorBundle] = {}

    # ── mask bit helpers ────────────────────────────────────────────
    @staticmethod
    def _mask_to_bits(mask: tuple) -> np.ndarray:
        s = set(mask)
        return np.array([1.0 if b in s else 0.0 for b in MASK_BITS],
                        dtype=np.float64)

    @staticmethod
    def _bits_to_mask(bits: np.ndarray) -> tuple:
        out = ["packet"]
        for i, b in enumerate(MASK_BITS):
            if bits[i] >= 0.5:
                out.append(b)
        return tuple(out)

    def _mask_distance(self, a: tuple, b: tuple) -> float:
        return len(set(a) ^ set(b)) / float(len(MASK_BITS))

    # ── scoring ─────────────────────────────────────────────────────
    def _score(self, cfg: SubstrateConfig, R: float,
               dtheta: np.ndarray) -> float:
        if self._center is None:
            return 0.0

        mask_d = self._mask_distance(cfg.feature_mask,
                                     self._center.feature_mask)
        r_span = max(max(self.r_values) - min(self.r_values), 1)
        r_d = abs(cfg.r - self._center.r) / float(r_span)
        nl_span = max(max(self.n_loops_values) - min(self.n_loops_values), 1)
        nl_d = abs(cfg.n_loops - self._center.n_loops) / float(nl_span)

        dist = self.w_mask * mask_d + self.w_r * r_d + self.w_nl * nl_d
        target = 1.0 - float(R)
        dist_cost = abs(dist - target)

        center_bits = self._mask_to_bits(self._center.feature_mask)
        cfg_bits = self._mask_to_bits(cfg.feature_mask)
        theta_cost = 0.0
        for i in range(len(MASK_BITS)):
            flipped = (cfg_bits[i] != center_bits[i])
            want_flip = (dtheta[i] < 0.0)
            if flipped != want_flip:
                theta_cost += self.theta_flip_penalty

        return float(dist_cost + theta_cost)

    # ── epsilon ─────────────────────────────────────────────────────
    def _current_epsilon(self) -> float:
        """
        Coupling drive for the field.

        "monitors": epsilon from the bundle of the current best
                    candidate. Falls back to best_reward if no bundle.
        "best_reward": epsilon = best reward so far, or 1.0 if none.
        """
        if not self._history:
            return 1.0

        best_rec = min(self._history, key=lambda r: r.reward)

        if self.epsilon_source == "monitors":
            bundle = self._bundles.get(best_rec.config)
            if bundle is not None:
                return float(epsilon_from_monitors(bundle))

        return float(best_rec.reward)

    # ── proposal ────────────────────────────────────────────────────
    def _propose(self) -> SubstrateConfig:
        eps = self._current_epsilon()
        self.field.step(epsilon=eps, W=self.W)
        R = self.field.order_parameter()
        dtheta = self.field.velocity(epsilon=eps, W=self.W)

        best = (min(self._history, key=lambda r: r.reward).config
                if self._history else None)
        if best is not None:
            self._center = best

        unvisited = [c for c in self._grid if c not in self._visited]
        if not unvisited:
            return best if best is not None else self._grid[0]

        if self._center is None:
            return unvisited[0]

        scores = [self._score(c, R, dtheta) for c in unvisited]
        return unvisited[int(np.argmin(scores))]

    # ── public interface ────────────────────────────────────────────
    def run(self, evaluate: Evaluator,
            iterations: Optional[int] = None,
            **metadata: Any) -> "OscillatorOrientedSearch":
        n = int(iterations) if iterations is not None else self.budget
        for _ in range(n):
            cfg = self._propose()
            if cfg in self._visited:
                break
            result = evaluate(cfg)
            if isinstance(result, tuple):
                reward, bundle = result
                self._bundles[cfg] = bundle
            else:
                reward = result
            self._visited.add(cfg)
            self._history.append(EvolutionRecord(
                config=cfg, reward=float(reward), metadata=dict(metadata)))
        return self

    # ── introspection ───────────────────────────────────────────────
    def history(self) -> list[EvolutionRecord]:
        return list(self._history)

    def best(self) -> Optional[EvolutionRecord]:
        if not self._history:
            return None
        return min(self._history, key=lambda r: r.reward)

    def ranked(self) -> list[EvolutionRecord]:
        return sorted(self._history, key=lambda r: r.reward)

    def n_visited(self) -> int:
        return len(self._visited)

    def coverage(self) -> float:
        return len(self._visited) / float(len(self._grid))

    def best_so_far(self) -> list[float]:
        out: list[float] = []
        cur = float("inf")
        for rec in self._history:
            cur = min(cur, rec.reward)
            out.append(cur)
        return out

    def field_state(self) -> dict:
        return {
            "theta": self.field.theta.tolist(),
            "R": self.field.order_parameter(),
            "omega": self.field.omega.tolist(),
        }

    def summary(self) -> dict:
        if not self._history:
            return {"n": 0}
        rewards = np.array([r.reward for r in self._history], dtype=np.float64)
        best = self.best()
        return {
            "n_evaluated": len(self._history),
            "n_grid": len(self._grid),
            "coverage": self.coverage(),
            "reward_min": float(rewards.min()),
            "reward_max": float(rewards.max()),
            "reward_mean": float(rewards.mean()),
            "best_config": {
                "r": best.config.r,
                "n_loops": best.config.n_loops,
                "feature_mask": list(best.config.feature_mask),
            },
            "best_reward": float(best.reward),
            "field_R": self.field.order_parameter(),
            "epsilon_source": self.epsilon_source,
            "n_bundles": len(self._bundles),
        }


__all__ = ["OscillatorOrientedSearch", "MASK_BITS", "Evaluator", "EvalReturn"]
