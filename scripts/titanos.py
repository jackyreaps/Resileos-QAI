#!/usr/bin/env python3
"""
Titanos — recurrent-depth quantum-classical prototype on the frozen contracts.

Confidence modes (conf_mode):
    sim        cosine only (baseline)
    mag        magnitude only (measured winner on current corpus)
    product    sim * mag
    min        min(sim, mag)
    composite  alpha*sim_norm + (1-alpha)*mag_norm

The "quantum" path is a labeled simulation (QUANTUM_SIM). Not real quantum.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resileos.core import CoreConfig, ResidualCore
from resileos.sigma import SigmaGate, SigmaAction
from resileos.abstention import (
    AbstentionInputs, AbstentionThresholds, route_signals,
    CONTINUE, REPULSE, CLEANUP, ABSTAIN,
)


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

    conf_mode: str = "mag"
    conf_alpha: float = 0.6

    sigma_E: float = 10.0
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


@dataclass
class Answer:
    value: str | None
    confidence: float
    status: str
    mode: str
    loops: int
    path: list[tuple[str, str, str]] = field(default_factory=list)
    reason: str = ""
    loop_history: list[dict] = field(default_factory=list)
    gate_state: str = ""


class Titanos:

    def __init__(self, cfg: TitanosConfig):
        self.cfg = cfg
        if cfg.m * cfg.n != cfg.dim:
            raise ValueError(f"m*n ({cfg.m*cfg.n}) must equal dim ({cfg.dim})")

        self.rng = np.random.default_rng(cfg.seed)
        self.core = ResidualCore(CoreConfig(m=cfg.m, n=cfg.n, r=cfg.r),
                                 seed=cfg.seed)

        self.acc = np.zeros(cfg.dim, dtype=np.int32)
        self._perm = self.rng.permutation(cfg.dim)
        self._perm_cache: dict[int, np.ndarray] = {0: np.arange(cfg.dim)}

        self.entities: dict[str, np.ndarray] = {}
        self.relations: dict[str, np.ndarray] = {}
        self.roles: dict[str, np.ndarray] = {}
        for name in ("S", "O"):
            self.roles[name] = self._bip()

        self.sigma = SigmaGate(E_sigma=cfg.E_sigma, k=cfg.sigma_k)
        self.thresholds = AbstentionThresholds(
            E_sat=cfg.E_sat, tau_sat=cfg.tau_sat, tau_low=cfg.tau_low,
        )

        self.facts: list[tuple[str, str, str]] = []

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

    # ── confidence ─────────────────────────────────────────────────────
    def _score_candidates(self, vec: np.ndarray,
                          exclude: set[str] | None = None,
                          ) -> list[tuple[str, float, float]]:
        exclude = exclude or set()
        D = float(self.cfg.dim)
        acc_f = self.acc.astype(np.float64)
        out: list[tuple[str, float, float]] = []
        for name, anchor in self.entities.items():
            if name in exclude:
                continue
            a = anchor.astype(np.float64)
            sim = float(np.dot(vec, anchor)) / D
            mag = abs(float(np.dot(acc_f, a))) / D
            out.append((name, sim, mag))
        return out

    def _cleanup(self, vec: np.ndarray,
                 exclude: set[str] | None = None,
                 ) -> tuple[str | None, float]:
        exclude = exclude or set()
        alpha = getattr(self.cfg, "conf_alpha", 0.6)
        mode = getattr(self.cfg, "conf_mode", "mag")
        D = float(self.cfg.dim)
        acc_f = self.acc.astype(np.float64)

        names: list[str] = []
        sims: list[float] = []
        mags: list[float] = []
        for name, anchor in self.entities.items():
            if name in exclude:
                continue
            a = anchor.astype(np.float64)
            names.append(name)
            sims.append(float(np.dot(vec, anchor)) / D)
            mags.append(abs(float(np.dot(acc_f, a))) / D)

        if not names:
            return None, 0.0

        s = np.array(sims, dtype=np.float64)
        m = np.array(mags, dtype=np.float64)

        if mode == "sim":
            conf = s
        elif mode == "mag":
            conf = m
        elif mode == "product":
            conf = s * m
        elif mode == "min":
            conf = np.minimum(s, m)
        elif mode == "composite":
            smax = s.max() + 1e-12
            mmax = m.max() + 1e-12
            conf = alpha * (s / smax) + (1.0 - alpha) * (m / mmax)
        else:
            raise ValueError(f"unknown conf_mode: {mode}")

        idx = int(np.argmax(conf))
        return names[idx], float(conf[idx])

    # ── learn ──────────────────────────────────────────────────────────
    def learn(self, subject: str, relation: str, obj: str) -> None:
        s, o = self._ent(subject), self._ent(obj)
        sr = self._slot("S", relation)
        orr = self._slot("O", relation)
        self.acc += (s * sr + o * orr).astype(np.int32)
        self.facts.append((subject, relation, obj))

    def _encode_probe(self, subject: str, relation: str,
                      inverse: bool = False) -> np.ndarray:
        s = self._ent(subject)
        slot = self._slot("O" if inverse else "S", relation)
        return (s * slot).astype(np.int8)

    # ── recurrent block ────────────────────────────────────────────────
    def _recurrent(self, initial_h: np.ndarray,
                   ) -> tuple[np.ndarray, list[dict], str, str]:
        h = initial_h.copy()
        history: list[dict] = []
        sqrt_dim = float(np.sqrt(self.cfg.dim))

        for i in range(self.cfg.n_loops):
            W = h.reshape(self.cfg.m, self.cfg.n).astype(np.float64)

            # DeltaS calibration: W is a reshape of a bipolar vector,
            # so ||W||_F is ~sqrt(dim) and normalizing by that gives
            # ~1. DeltaS = 1/(1+1) = 0.5, safely above tau_low.
            norm_W = float(np.linalg.norm(W)) / sqrt_dim
            DeltaS = float(1.0 / (1.0 + norm_W))

            packet = self.core.step(
                W,
                version=self.cfg.packet_version,
                mu=int(i % 2),
                F_res=float(np.mean(W)),
                DeltaS=DeltaS,
            )

            W_hat = (packet.Ub @ packet.Vb).astype(np.float64)
            h_compressed = W_hat.reshape(self.cfg.dim)
            scar = float(np.linalg.norm(packet.Lambda))
            delta = float(np.abs(h - h_compressed).mean())

            gate_action = self.sigma.evaluate(
                scar_energy=scar,
                mu=int(packet.mu),
                volume_ok=bool(packet.volume_ok),
            )

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

    # ── quantum-sim ────────────────────────────────────────────────────
    def _quantum_sim(self, probe: np.ndarray,
                     exclude: set[str],
                     ) -> tuple[str | None, float]:
        readout = self._readout()
        candidates = []
        for _ in range(self.cfg.quantum_samples):
            flip_mask = self.rng.random(self.cfg.dim) < 0.05
            perturbed = np.where(flip_mask, -probe, probe).astype(np.int8)
            candidates.append((readout * perturbed).astype(np.int8))
        superposition = np.sum(np.stack(candidates), axis=0)
        measured = np.where(superposition >= 0, 1, -1).astype(np.int8)
        return self._cleanup(measured, exclude=exclude)

    # ── ask ────────────────────────────────────────────────────────────
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
                      path=[(a, "->", b), (c, "->", best)])

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
            "conf_mode": getattr(self.cfg, "conf_mode", "mag"),
            "conf_alpha": float(getattr(self.cfg, "conf_alpha", 0.6)),
        }

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


_PATTERNS = [
    (re.compile(r"who is the (\w+) of (\w+)", re.I),
     lambda m: (m.group(2), m.group(1), True)),
    (re.compile(r"(?:who|what) is (\w+)'s (\w+)", re.I),
     lambda m: (m.group(1), m.group(2), False)),
    (re.compile(r"what is the (\w+) of (\w+)", re.I),
     lambda m: (m.group(2), m.group(1), True)),
    (re.compile(r"^(\w+)\s+(\w+)$", re.I),
     lambda m: (m.group(1), m.group(2), False)),
]


def parse_query(text: str) -> tuple[str, str, bool] | None:
    for pat, build in _PATTERNS:
        m = pat.search(text.strip())
        if m:
            return build(m)
    return None


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=None)
    args = p.parse_args()

    cfg = TitanosConfig.from_json(args.config) if args.config else TitanosConfig()
    titan = Titanos(cfg)
    print(f"conf_mode = {cfg.conf_mode}  alpha = {cfg.conf_alpha}")

    facts = [
        ("Uranus", "parent_of", "Cronus"), ("Cronus", "parent_of", "Zeus"),
        ("Cronus", "parent_of", "Poseidon"), ("Cronus", "parent_of", "Hades"),
        ("Zeus", "parent_of", "Ares"), ("Zeus", "parent_of", "Athena"),
        ("Zeus", "domain", "sky"), ("Poseidon", "domain", "sea"),
        ("Hades", "domain", "underworld"), ("Ares", "domain", "war"),
        ("Athena", "domain", "wisdom"), ("Uranus", "is_a", "primordial"),
        ("Cronus", "is_a", "titan"), ("Zeus", "is_a", "olympian"),
        ("Poseidon", "is_a", "olympian"), ("Hades", "is_a", "olympian"),
        ("Ares", "is_a", "olympian"), ("Athena", "is_a", "olympian"),
    ]
    for s, r, o in facts:
        titan.learn(s, r, o)

    for subj, rel in [("Zeus", "domain"), ("Zeus", "parent_of")]:
        a = titan.ask(subj, rel)
        print(f"{subj} --{rel}--> {a.value} [{a.mode} conf={a.confidence:.4f}]")

    for subj, rel in [("Zeus", "capital_of"), ("Odin", "parent_of")]:
        a = titan.ask(subj, rel)
        print(f"{subj} --{rel}--> ? [{a.status} conf={a.confidence:.4f}]")
