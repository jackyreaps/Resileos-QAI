#!/usr/bin/env python3
"""
Titanos — recurrent-depth quantum-classical prototype on the frozen contracts.

Architecture:
    Prelude         encode query into a hyperdimensional probe
    Recurrent Block frozen ResidualCore applied N times, weight-shared
    Router          SigmaGate → route_signals → CLASSICAL | QUANTUM_SIM | ABSTAIN
    Coda            substrate readout, cleanup, provenance

Fixes applied vs the first draft:
  - Consecutive volume failures tracked; escalation via SigmaGate (k=3).
  - Routing uses abstention.route_signals precedence (sigma1 > volume > machine).
  - Packet version pinned to "1.0.0".
  - Residual exponents emitted as int16 clamped to [-16,+16] (via core).
  - Quantum path labeled QUANTUM_SIM everywhere, never as real quantum.
  - Core treated as frozen: no gradient, no mutation of Λ / guard / schedule.
  - Config loads from JSON; substrate persists to disk.
  - Optional thin NLP front-end; not on the reasoning path.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.core import CoreConfig, ResidualCore
from resileos.sigma import SigmaGate, SigmaAction
from resileos.abstention import (
    AbstentionInputs, AbstentionThresholds, route_signals,
    CONTINUE, REPULSE, CLEANUP, ABSTAIN,
)


# ═══════════════════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════════════════
@dataclass
class TitanosConfig:
    packet_version: str = "1.0.0"
    dim: int = 10000
    m: int = 100
    n: int = 100
    r: int = 8
    seed: int = 1337
    n_loops: int = 12

    classical_conf: float = 0.09
    abstention_gate: float = 0.035
    quantum_samples: int = 16
    convergence_threshold: float = 0.02

    sigma_E: float = 0.35
    sigma_k: int = 3

    N_warm: int = 512
    E_sat: float = 10.0
    E_sigma: float = 10.0
    tau_sat: float = 0.9
    tau_low: float = 0.1

    X: float = 70.0
    Y: int = 3
    seed_list: tuple[int, ...] = (0, 1, 2)
    scar_var_floor: float = 0.0
    deltaS_range_floor: float = 0.0
    drift_ratio_floor: float = 0.0

    @classmethod
    def from_json(cls, path: str | Path) -> "TitanosConfig":
        raw = json.loads(Path(path).read_text())
        if "seed_list" in raw:
            raw["seed_list"] = tuple(raw["seed_list"])
        return cls(**raw)


# ═══════════════════════════════════════════════════════════════════════════
# Answer
# ═══════════════════════════════════════════════════════════════════════════
@dataclass
class Answer:
    value: str | None
    confidence: float
    status: str          # ACCEPTED | ABSTAINED
    mode: str            # CLASSICAL | QUANTUM_SIM | ABSTAIN
    loops: int
    path: list[tuple[str, str, str]] = field(default_factory=list)
    reason: str = ""
    loop_history: list[dict] = field(default_factory=list)
    gate_state: str = ""


# ═══════════════════════════════════════════════════════════════════════════
# Titanos
# ═══════════════════════════════════════════════════════════════════════════
class Titanos:

    def __init__(self, cfg: TitanosConfig):
        self.cfg = cfg
        if cfg.m * cfg.n != cfg.dim:
            raise ValueError(f"m*n ({cfg.m*cfg.n}) must equal dim ({cfg.dim})")

        self.rng = np.random.default_rng(cfg.seed)

        # Frozen core (no gradients, no mutation of Λ / guard / schedule)
        self.core = ResidualCore(CoreConfig(m=cfg.m, n=cfg.n, r=cfg.r),
                                 seed=cfg.seed)

        # Substrate
        self.acc = np.zeros(cfg.dim, dtype=np.int32)
        self._perm = self.rng.permutation(cfg.dim)
        self._perm_cache: dict[int, np.ndarray] = {0: np.arange(cfg.dim)}

        self.entities: dict[str, np.ndarray] = {}
        self.relations: dict[str, np.ndarray] = {}
        self.roles: dict[str, np.ndarray] = {}
        for name in ("S", "O"):
            self.roles[name] = self._bip()

        # Router
        self.sigma = SigmaGate(E_sigma=cfg.E_sigma, k=cfg.sigma_k)
        self.thresholds = AbstentionThresholds(
            E_sat=cfg.E_sat, tau_sat=cfg.tau_sat, tau_low=cfg.tau_low,
        )

        self.facts: list[tuple[str, str, str]] = []

    # ── VSA ────────────────────────────────────────────────────────────
    def _bip(self) -> np.ndarray:
        return self.rng.choice([-1, 1], size=self.cfg.dim).astype(np.int8)

    def _perm_k(self, k: int) -> np.ndarray:
        if k in self._perm_cache:
            return self._perm_cache[k]
        largest = max(self._perm_cache)
        idx = self._perm_cache[largest].copy()
        for _ in range(k - largest):
            idx = self._perm[idx]
        if k <= 256:
            self._perm_cache[k] = idx
        return idx

    def _ent(self, name: str) -> np.ndarray:
        if name not in self.entities:
            self.entities[name] = self._bip()
        return self.entities[name]

    def _rel(self, name: str) -> np.ndarray:
        if name not in self.relations:
            self.relations[name] = self._bip()
        return self.relations[name]

    def _slot(self, role: str, relation: str) -> np.ndarray:
        return (self.roles[role] * self._rel(relation)).astype(np.int8)

    def _readout(self) -> np.ndarray:
        return np.where(self.acc >= 0, 1, -1).astype(np.int8)

    def _cleanup(self, vec: np.ndarray,
                 exclude: set[str] | None = None) -> tuple[str | None, float]:
        exclude = exclude or set()
        best, best_sim = None, -1.0
        for name, anchor in self.entities.items():
            if name in exclude:
                continue
            sim = float(np.dot(vec, anchor)) / self.cfg.dim
            if sim > best_sim:
                best_sim, best = sim, name
        return best, best_sim

    # ── Learn ──────────────────────────────────────────────────────────
    def learn(self, subject: str, relation: str, obj: str) -> None:
        s, o = self._ent(subject), self._ent(obj)
        sr = self._slot("S", relation)
        orr = self._slot("O", relation)
        self.acc += (s * sr + o * orr).astype(np.int32)
        self.facts.append((subject, relation, obj))

    # ── Prelude ────────────────────────────────────────────────────────
    def _encode_probe(self, subject: str, relation: str,
                      inverse: bool = False) -> np.ndarray:
        s = self._ent(subject)
        slot = self._slot("O" if inverse else "S", relation)
        return (s * slot).astype(np.int8)

    # ── Recurrent block ────────────────────────────────────────────────
    def _recurrent(self, initial_h: np.ndarray,
                   ) -> tuple[np.ndarray, list[dict], str, str]:
        """
        Returns (refined_h, history, exit_reason, gate_state).
        exit_reason ∈ {"CONVERGED", "MAX_LOOPS", "SIGMA1", "ABSTAIN"}
        """
        h = initial_h.copy()
        history: list[dict] = []

        for i in range(self.cfg.n_loops):
            W = h.reshape(self.cfg.m, self.cfg.n).astype(np.float64)
            packet = self.core.step(
                W,
                version=self.cfg.packet_version,
                mu=int(i % 2),
                F_res=float(np.mean(W)),
                DeltaS=float(1.0 / (1.0 + np.linalg.norm(W))),
            )

            W_hat = (packet.Ub @ packet.Vb).astype(np.float64)
            h_compressed = W_hat.reshape(self.cfg.dim)
            scar = float(np.linalg.norm(packet.Lambda))
            delta = float(np.abs(h - h_compressed).mean())

            # Sigma-1 gate: tracks consecutive volume failures internally.
            gate_action = self.sigma.evaluate(
                scar_energy=scar,
                mu=int(packet.mu),
                volume_ok=bool(packet.volume_ok),
            )

            # Route using the frozen precedence (RES-302 / RES-303):
            # sigma1 > volume_ok > abstention machine.
            inputs = AbstentionInputs(
                DeltaS=float(packet.DeltaS),
                mu=int(packet.mu),
                scar_energy=scar,
                volume_ok=bool(packet.volume_ok),
            )
            sigma_arg = gate_action.value if gate_action != SigmaAction.NONE else None
            state = route_signals(inputs, self.thresholds, sigma_arg)

            history.append({
                "loop": i,
                "scar_energy": scar,
                "delta": delta,
                "mu": int(packet.mu),
                "DeltaS": float(packet.DeltaS),
                "rank": int(packet.rank),
                "volume_ok": bool(packet.volume_ok),
                "sigma1_action": gate_action.value,
                "gate_state": state,
                "packet_hash": packet.packet_hash[:12],
            })

            if state == CLEANUP:
                h = initial_h.copy()
                continue
            if state == ABSTAIN:
                return h_compressed, history, "ABSTAIN", state
            if delta < self.cfg.convergence_threshold:
                return h_compressed, history, "CONVERGED", state

            h = h_compressed

        return h, history, "MAX_LOOPS", history[-1]["gate_state"]

    # ── Quantum-simulated retrieval (labeled) ──────────────────────────
    def _quantum_sim(self, probe: np.ndarray,
                     exclude: set[str],
                     ) -> tuple[str | None, float]:
        """
        Simulated quantum retrieval: bundle K sparse perturbations
        (superposition), hard readout (measurement), cleanup.

        Labeled QUANTUM_SIM. Not a real quantum computation.
        """
        readout = self._readout()
        candidates = []
        for _ in range(self.cfg.quantum_samples):
            flip_mask = self.rng.random(self.cfg.dim) < 0.05
            perturbed = np.where(flip_mask, -probe, probe).astype(np.int8)
            candidates.append((readout * perturbed).astype(np.int8))
        superposition = np.sum(np.stack(candidates), axis=0)
        measured = np.where(superposition >= 0, 1, -1).astype(np.int8)
        return self._cleanup(measured, exclude=exclude)

    # ── Top-level ask ──────────────────────────────────────────────────
    def _ask(self, subject: str, relation: str, inverse: bool) -> Answer:
        if subject not in self.entities:
            return Answer(None, 0.0, "ABSTAINED", "ABSTAIN", 0,
                          reason=f"unknown entity '{subject}'")

        probe = self._encode_probe(subject, relation, inverse=inverse)
        refined, history, exit_reason, gate_state = self._recurrent(probe)

        if exit_reason == "ABSTAIN":
            return Answer(None, 0.0, "ABSTAINED", "ABSTAIN",
                          loops=len(history),
                          loop_history=history,
                          gate_state=gate_state,
                          reason="sigma-1 gate routed to ABSTAIN")

        readout = self._readout()
        retrieved = (readout * refined).astype(np.int8)
        best, sim = self._cleanup(retrieved, exclude={subject})

        if sim >= self.cfg.classical_conf:
            mode = "CLASSICAL"
        elif sim >= self.cfg.abstention_gate:
            best_q, sim_q = self._quantum_sim(refined, exclude={subject})
            if sim_q > sim:
                best, sim = best_q, sim_q
            mode = "QUANTUM_SIM"
        else:
            return Answer(None, sim, "ABSTAINED", "ABSTAIN",
                          loops=len(history),
                          loop_history=history,
                          gate_state=gate_state,
                          reason=f"similarity {sim:.4f} < gate {self.cfg.abstention_gate}")

        if best is None or sim < self.cfg.abstention_gate:
            return Answer(None, sim, "ABSTAINED", mode,
                          loops=len(history),
                          loop_history=history,
                          gate_state=gate_state,
                          reason=f"post-quantum similarity {sim:.4f} below gate")

        path = [(best, relation, subject)] if inverse else [(subject, relation, best)]
        return Answer(best, sim, "ACCEPTED", mode,
                      loops=len(history), path=path,
                      loop_history=history, gate_state=gate_state)

    def ask(self, subject: str, relation: str) -> Answer:
        return self._ask(subject, relation, inverse=False)

    def ask_inverse(self, obj: str, relation: str) -> Answer:
        return self._ask(obj, relation, inverse=True)

    def chain(self, start: str, relations: list[str]) -> Answer:
        current, path, confidence = start, [], 1.0
        total_loops = 0
        modes: list[str] = []
        history_acc: list[dict] = []

        for rel in relations:
            ans = self.ask(current, rel)
            total_loops += ans.loops
            modes.append(ans.mode)
            history_acc.extend(ans.loop_history)
            if ans.status == "ABSTAINED":
                return Answer(None, confidence, "ABSTAINED", "ABSTAIN",
                              total_loops, path=path,
                              loop_history=history_acc,
                              reason=f"chain broke at '{current} --{rel}--> ?'")
            path.extend(ans.path)
            confidence *= ans.confidence
            current = ans.value

        mode = "QUANTUM_SIM" if "QUANTUM_SIM" in modes else "CLASSICAL"
        return Answer(current, confidence, "ACCEPTED", mode,
                      total_loops, path=path, loop_history=history_acc)

    def analogy(self, a: str, b: str, c: str) -> Answer:
        for name in (a, b, c):
            if name not in self.entities:
                return Answer(None, 0.0, "ABSTAINED", "ABSTAIN", 0,
                              reason=f"unknown entity '{name}'")
        transform = (self._ent(a) * self._ent(b)).astype(np.int8)
        candidate = (self._ent(c) * transform).astype(np.int8)
        best, sim = self._cleanup(candidate, exclude={a, b, c})
        if sim < self.cfg.abstention_gate:
            return Answer(None, sim, "ABSTAINED", "CLASSICAL", 0,
                          reason=f"analogy similarity {sim:.4f} below gate")
        return Answer(best, sim, "ACCEPTED", "CLASSICAL", 0,
                      path=[(a, "→", b), (c, "→", best)])

    # ── Introspection ──────────────────────────────────────────────────
    def explain(self, ans: Answer) -> str:
        head = (f"[{ans.status}] mode={ans.mode} loops={ans.loops} "
                f"conf={ans.confidence:.4f}")
        if ans.gate_state:
            head += f" gate={ans.gate_state}"
        if ans.status == "ABSTAINED":
            return f"{head}\n  reason: {ans.reason}"
        lines = [head, f"  answer: {ans.value}"]
        for s, r, o in ans.path:
            lines.append(f"    {s} --{r}--> {o}")
        return "\n".join(lines)

    def loop_trace(self, ans: Answer) -> str:
        if not ans.loop_history:
            return "(no loop history)"
        lines = ["loop | scar    | delta   | mu | DeltaS | rank | vol | gate"]
        lines.append("-" * 68)
        for h in ans.loop_history:
            lines.append(
                f"  {h['loop']:2d} | {h['scar_energy']:.4f} | "
                f"{h['delta']:.4f} | {h['mu']}  | "
                f"{h['DeltaS']:.4f} | {h['rank']:4d} | "
                f"{'ok' if h['volume_ok'] else 'BAD':>3s} | {h['gate_state']}"
            )
        return "\n".join(lines)

    def stats(self) -> dict:
        return {
            "dim": self.cfg.dim,
            "core_matrix": f"{self.cfg.m}x{self.cfg.n}",
            "latent_rank": self.cfg.r,
            "max_loops": self.cfg.n_loops,
            "facts": len(self.facts),
            "entities": len(self.entities),
            "relations": len(self.relations),
            "accumulator_energy": int(np.sum(self.acc.astype(np.int64) ** 2)),
            "packet_version": self.cfg.packet_version,
        }

    # ── Persistence ────────────────────────────────────────────────────
    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps({
            "cfg": {**asdict(self.cfg), "seed_list": list(self.cfg.seed_list)},
            "acc": self.acc.tolist(),
            "entities": {k: v.tolist() for k, v in self.entities.items()},
            "relations": {k: v.tolist() for k, v in self.relations.items()},
            "roles": {k: v.tolist() for k, v in self.roles.items()},
            "facts": [list(t) for t in self.facts],
            "perm": self._perm.tolist(),
        }))

    @classmethod
    def load(cls, path: str | Path) -> "Titanos":
        raw = json.loads(Path(path).read_text())
        cfg = TitanosConfig(**raw["cfg"])
        obj = cls(cfg)
        obj.acc = np.array(raw["acc"], dtype=np.int32)
        obj.entities = {k: np.array(v, dtype=np.int8) for k, v in raw["entities"].items()}
        obj.relations = {k: np.array(v, dtype=np.int8) for k, v in raw["relations"].items()}
        obj.roles = {k: np.array(v, dtype=np.int8) for k, v in raw["roles"].items()}
        obj.facts = [tuple(t) for t in raw["facts"]]
        obj._perm = np.array(raw["perm"])
        obj._perm_cache = {0: np.arange(cfg.dim)}
        return obj


# ═══════════════════════════════════════════════════════════════════════════
# Thin NLP front-end (optional; not on the reasoning path)
# ═══════════════════════════════════════════════════════════════════════════
_PATTERNS = [
    # "who is the parent of Zeus" / "who is parent of zeus"
    (re.compile(r"who is the (\w+) of (\w+)", re.I), lambda m: (m.group(2), m.group(1), True)),
    # "who is Zeus's parent" / "what is Zeus's domain"
    (re.compile(r"(?:who|what) is (\w+)'s (\w+)", re.I), lambda m: (m.group(1), m.group(2), False)),
    # "what is the parent of Zeus"
    (re.compile(r"what is the (\w+) of (\w+)", re.I), lambda m: (m.group(2), m.group(1), True)),
    # "zeus parent" (compact)
    (re.compile(r"^(\w+)\s+(\w+)$", re.I), lambda m: (m.group(1), m.group(2), False)),
]


def parse_query(text: str) -> tuple[str, str, bool] | None:
    for pat, build in _PATTERNS:
        m = pat.search(text.strip())
        if m:
            return build(m)
    return None


# ═══════════════════════════════════════════════════════════════════════════
# DEMO
# ═══════════════════════════════════════════════════════════════════════════
def _demo():
    cfg = TitanosConfig(dim=10000, m=100, n=100, r=8, n_loops=12, seed=1337)
    titan = Titanos(cfg)

    print("=" * 72)
    print("Titanos — recurrent-depth quantum-classical prototype")
    print("=" * 72)
    for k, v in titan.stats().items():
        print(f"  {k:18s} = {v}")
    print()

    facts = [
        ("Uranus",   "parent_of", "Cronus"),
        ("Cronus",   "parent_of", "Zeus"),
        ("Cronus",   "parent_of", "Poseidon"),
        ("Cronus",   "parent_of", "Hades"),
        ("Zeus",     "parent_of", "Ares"),
        ("Zeus",     "parent_of", "Athena"),
        ("Zeus",     "domain",    "sky"),
        ("Poseidon", "domain",    "sea"),
        ("Hades",    "domain",    "underworld"),
        ("Ares",     "domain",    "war"),
        ("Athena",   "domain",    "wisdom"),
        ("Uranus",   "is_a",      "primordial"),
        ("Cronus",   "is_a",      "titan"),
        ("Zeus",     "is_a",      "olympian"),
        ("Poseidon", "is_a",      "olympian"),
        ("Hades",    "is_a",      "olympian"),
        ("Ares",     "is_a",      "olympian"),
        ("Athena",   "is_a",      "olympian"),
    ]
    for s, r, o in facts:
        titan.learn(s, r, o)
    print(f"[learned {len(facts)} facts]\n")

    print("── Single-hop ──")
    for s, r in [("Zeus", "parent_of"), ("Zeus", "domain"), ("Cronus", "parent_of")]:
        a = titan.ask(s, r)
        print(f"  {s} --{r}--> {a.value or '(abstain)'}   "
              f"[{a.mode}, {a.loops} loops, conf {a.confidence:.4f}]")

    print("\n── Inverse ──")
    for o, r in [("Zeus", "parent_of"), ("Athena", "parent_of"), ("sea", "domain")]:
        a = titan.ask_inverse(o, r)
        print(f"  ? --{r}--> {o}  =  {a.value or '(abstain)'}   "
              f"[{a.mode}, conf {a.confidence:.4f}]")

    print("\n── Multi-hop ──")
    print(titan.explain(titan.chain("Uranus", ["parent_of", "parent_of", "parent_of"])))

    print("\n── Analogy ──")
    print(titan.explain(titan.analogy("Zeus", "sky", "Poseidon")))
    print(titan.explain(titan.analogy("Poseidon", "sea", "Hades")))

    print("\n── Abstention ──")
    for s, r in [("Zeus", "capital_of"), ("Odin", "parent_of")]:
        a = titan.ask(s, r)
        print(f"  {s} --{r}--> ?")
        print(f"    {titan.explain(a)}")

    print("\n── NLP front-end ──")
    for text in ["Who is the parent of Zeus?",
                 "Who is Zeus's parent?",
                 "What is Poseidon's domain?"]:
        parsed = parse_query(text)
        print(f"  '{text}'")
        print(f"    parsed → {parsed}")
        if parsed:
            subj, rel, inv = parsed
            ans = titan.ask_inverse(subj, rel) if inv else titan.ask(subj, rel)
            print(f"    → {ans.value or '(abstain)'}  [{ans.mode}]")

    print("\n── Loop trace (Zeus → parent_of) ──")
    a = titan.ask("Zeus", "parent_of")
    print(titan.loop_trace(a))
    print()
    print(titan.explain(a))


if __name__ == "__main__":
    _demo()
