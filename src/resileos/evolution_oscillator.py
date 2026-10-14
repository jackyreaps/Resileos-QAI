"""Oscillator-oriented discrete grid search.

Wraps the same grid as EvolutionLoop. Uses a KuramotoField to bias the order
in which grid candidates are proposed.

Orientation:
    - Three oscillators, one per optional mask bit (csi, order_parameter,
      direction).
    - dtheta_i < 0 -> prefer flipping mask bit i.
    - dtheta_i >= 0 -> prefer keeping mask bit i.

Level:
    - R sets the target distance from the current best config.
    - R = 1 (locked) -> propose near the best.
    - R = 0 (exploring) -> propose far from the best.

Coupling drive (epsilon_source):
    - "best_reward" (default): epsilon = best reward so far.
    - "monitors": epsilon = epsilon_from_monitors(bundle of current best).
      Requires the evaluator to return (reward, MonitorBundle). If a bundle
      is not available, falls back to best_reward.

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
            SubstrateConfig(
                r=self.r_values[0], n_loops=self.n_loops_values[0], feature_mask=m
            )
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
                f"field must have {len(MASK_BITS)} oscillators, got {field.r}"
            )
        self.field = field
        self.W = np.ones((len(MASK_BITS), len(MASK_BITS))) - np.eye(
            len(MASK_BITS)
        )

        total = mask_weight + r_weight + n_loops_weight
        if total <= 0.0:
            raise ValueError("score weights must not all be zero")
        self.w_mask = float(mask_weight) / total
        self.w_r = float(r_weight) / total
        self.w_nl = float(n_loops_weight) / total
        self.theta_flip_penalty = float(theta_flip_penalty)

        self._grid = _all_grid_candidates(
            self.r_values, self.n_loops_values, self.feature_masks
        )
        self._visited: set[SubstrateConfig] = set()
        self._history: list[EvolutionRecord] = []
        self._center: Optional[SubstrateConfig] = None
        self._bundles: dict[SubstrateConfig, MonitorBundle] = {}

    # ── mask bit helpers ────────────────────────────────────────────
    @staticmethod
    def _mask_to_bits(mask: tuple) -> np.ndarray:
        s = set(mask)
        return np.array(
            [1.0 if b in s else 0.0 for b in MASK_BITS], dtype=np.float64
        )

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
    def _score(self, cfg: SubstrateConfig, R: float, dtheta: np.ndarray) -> float:
        if self._center is None:
            return 0.0
        mask_d = self._mask_distance(cfg.feature_mask, self._center.feature_mask)
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
            flipped = cfg_bits[i] != center_bits[i]
            want_flip = dtheta[i] < 0.0
            if flipped != want_flip:
                theta_cost += self.theta_flip_penalty
        return float(dist_cost + theta_cost)

    # ── epsilon ─────────────────────────────────────────────────────
    def _current_epsilon(self) -> float:
        """Coupling drive for the field.

        "monitors": epsilon from the bundle of the current best candidate.
            Falls back to best_reward if no bundle.
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
