#!/usr/bin/env python3
"""Amplitude amplification (Grover's algorithm) reference implementation.

Classical state-vector simulation. Pedagogical artifact for the RES-600
series. No connection to the residual core, packet schema, substrate, or
bridge metric. Runs on CPU, deterministic, no QPU.

This file exists as the comparison point if a real quantum backend is
ever wired into the 600-series. It is not wired into anything now. Do
not import it from src/resileos/ and do not expose it via the API.

Usage:
    python run_amplitude_amplification.py --n-qubits 4 --target 11
    python run_amplitude_amplification.py --n-qubits 6 --target 42 --iterations 5
"""
from __future__ import annotations

import argparse
import math

import numpy as np


class GroverSimulator:
    """Textbook Grover on a NumPy state vector.

    N = 2^n_qubits. State is a length-N complex vector, unit L2 norm.
    """

    def __init__(self, n_qubits: int, target: int) -> None:
        if n_qubits < 1:
            raise ValueError("n_qubits must be >= 1")
        self.n_qubits = int(n_qubits)
        self.N = 1 << self.n_qubits
        if not (0 <= target < self.N):
            raise ValueError(
                f"target {target} out of range [0, {self.N})"
            )
        self.target = int(target)
        self.state = (
            np.ones(self.N, dtype=np.complex128) / math.sqrt(self.N)
        )

    @property
    def optimal_iterations(self) -> int:
        """floor(π/4 · √N). The iteration count that maximises p(target)."""
        return int(math.floor((math.pi / 4.0) * math.sqrt(self.N)))

    def norm(self) -> float:
        return float(np.linalg.norm(self.state))

    def p_target(self) -> float:
        return float(abs(self.state[self.target]) ** 2)

    def oracle(self) -> None:
        """Phase flip on the target amplitude."""
        self.state[self.target] *= -1.0

    def diffusion(self) -> None:
        """Reflect about the mean amplitude."""
        mean = complex(np.mean(self.state))
        self.state = 2.0 * mean - self.state

    def step(self) -> None:
        self.oracle()
        self.diffusion()

    def run(
        self,
        iterations: int | None = None,
        *,
        verify_norm: bool = True,
        atol: float = 1e-9,
    ) -> dict:
        """Run the algorithm and return a summary dict.

        If iterations is None, use the optimal count. verify_norm
        asserts the state vector stays unit-L2 at every step (Grover
        preserves norm by construction; a drift means a bug).
        """
        if iterations is None:
            iterations = self.optimal_iterations
        if iterations < 0:
            raise ValueError("iterations must be >= 0")

        history: list[dict] = [{
            "step": 0,
            "p_target": self.p_target(),
            "norm": self.norm(),
        }]
        for i in range(iterations):
            self.step()
            n = self.norm()
            if verify_norm and abs(n - 1.0) > atol:
                raise RuntimeError(
                    f"norm drifted at step {i + 1}: {n:.12f}"
                )
            history.append({
                "step": i + 1,
                "p_target": self.p_target(),
                "norm": n,
            })

        return {
            "n_qubits": self.n_qubits,
            "N": self.N,
            "target": self.target,
            "optimal_iterations": self.optimal_iterations,
            "iterations_run": iterations,
            "p_target_initial": history[0]["p_target"],
            "p_target_final": history[-1]["p_target"],
            "history": history,
        }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-qubits", type=int, default=4)
    ap.add_argument("--target", type=int, default=11)
    ap.add_argument(
        "--iterations", type=int, default=None,
        help="default: floor(pi/4 * sqrt(N))",
    )
    ap.add_argument(
        "--no-verify", action="store_true",
        help="skip the per-step norm check",
    )
    args = ap.parse_args()

    sim = GroverSimulator(args.n_qubits, args.target)
    result = sim.run(
        args.iterations, verify_norm=not args.no_verify,
    )

    print(f"N                = {result['N']}")
    print(f"target           = {result['target']}")
    print(f"optimal iters    = {result['optimal_iterations']}")
    print(f"iters run        = {result['iterations_run']}")
    print(f"p(target) init   = {result['p_target_initial']:.6f}")
    print()
    print(f"{'step':>4}  {'p(target)':>12}  {'norm':>12}")
    for h in result["history"]:
        print(
            f"{h['step']:>4}  {h['p_target']:>12.8f}  "
            f"{h['norm']:>12.8f}"
        )
    print()
    print(f"p(target) final  = {result['p_target_final']:.8f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
