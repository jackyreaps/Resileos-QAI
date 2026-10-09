#!/usr/bin/env python3
"""
Titanos — recurrent-depth quantum-classical prototype on the frozen contracts.

Storage:
    Directed MAP binding: acc += s ⊗ r ⊗ permute(o)
    The permutation makes (a, r, b) and (b, r, a) different vectors.

Retrieval:
    Direct unbind first. Recurrent refinement only if classical conf is weak.
    Quantum-sim only if recurrent conf is still weak.

Confidence modes: sim | mag | product | min | composite.
    mag is candidate-specific, computed from the query-specific retrieved
    vector — not from the global accumulator (which would bias toward
    frequently occurring entities like Zeus).

The "quantum" path is a labeled simulation (QUANTUM_SIM). Not real quantum.
"""
from __future__ import annotations

import dataclasses
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
    sigma1_k: int = 3
    N_warm: int = 512
    E_sat: float = 10.0
    E_sigma: float = 10.0
    tau_sat: float = 0.9
    tau_low: float = 0.1
    X: float = 70.0
    Y: int = 3
    seed_list: tuple = (0, 1, 2)
    scar_var_floor: float = 0.0
    deltaS_range_floor: float = 0.0
    drift_ratio_floor: float = 0.0

    @classmethod
    def from_json(cls, path):
        raw = json.loads(Path(path).read_text())
        if "seed_list" in raw:
            raw["seed_list"] = tuple(raw["seed_list"])
        valid = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in raw.items() if k in valid})


@dataclass
class Answer:
    value: str | None
    confidence: float
    status: str
    mode: str
    loops: int
    path: list = field(default_factory=list)
    reason: str = ""
    loop_history: list = field(default_factory=list)
    gate_state: str = ""


class Titanos:

    def __init__(self, cfg):
        self.cfg = cfg
        if cfg.m * cfg.n != cfg.dim:
            raise ValueError(f"m*n ({cfg.m*cfg.n}) != dim ({cfg.dim})")
        self.rng = np.random.default_rng(cfg.seed)
        self.core = ResidualCore(CoreConfig(m=cfg.m, n=cfg.n, r=cfg.r), seed=cfg.seed)
        self.acc = np.zeros(cfg.dim, dtype=np.int32)
        self._perm = self.rng.permutation(cfg.dim)
        self._perm_inv = np.argsort(self._perm)
        self._perm_cache = {0: np.arange(cfg.dim)}
        self.entities = {}
        self.relations = {}
        self.sigma = SigmaGate(E_sigma=cfg.E_sigma, k=cfg.sigma1_k)
        self.thresholds = AbstentionThresholds(
            E_sat=cfg.E_sat, tau_sat=cfg.tau_sat, tau_low=cfg.tau_low)
        self.facts = []

    def _bip(self):
        return self.rng.choice([-1, 1], size=self.cfg.dim).astype(np.int8)

    def _permute(self, v):
        return v[self._perm]

    def _unpermute(self, v):
        return v[self._perm_inv]

    def _ent(self, name):
        if name not in self.entities:
            self.entities[name] = self._bip()
        return self.entities[name]

    def _rel(self, name):
        if name not in self.relations:
            self.relations[name] = self._bip()
        return self.relations[name]

    def _readout(self):
        return np.where(self.acc >= 0, 1, -1).astype(np.int8)

    # ── learn ──────────────────────────────────────────────────────────
    def learn(self, subject, relation, obj):
        s = self._ent(subject).astype(np.int32)
        o = self._ent(obj).astype(np.int32)
        r = self._rel(relation).astype(np.int32)
        triple = s * r * self._permute(o).astype(np.int32)
        self.acc += triple
        self.facts.append((subject, relation, obj))

    # ── confidence ─────────────────────────────────────────────────────
    def _score_candidates(self, retrieved, exclude=None):
        """retrieved is query-specific. mag and sim both come from it."""
        exclude = exclude or set()
        D = float(self.cfg.dim)
        retrieved_f = retrieved.astype(np.float64)
        ret_bip = np.where(retrieved >= 0, 1, -1).astype(np.int8)
        out = []
        for name, anchor in self.entities.items():
            if name in exclude:
                continue
            sim = float(np.dot(ret_bip, anchor)) / D
            mag = abs(float(np.dot(retrieved_f, anchor.astype(np.float64)))) / D
            out.append((name, sim, mag))
        return out

    def _cleanup(self, retrieved, exclude=None):
        scores = self._score_candidates(retrieved, exclude)
        if not scores:
            return None, 0.0
        names = [n for n, _, _ in scores]
        s = np.array([x[1] for x in scores])
        m = np.array([x[2] for x in scores])
        mode = self.cfg.conf_mode
        alpha = self.cfg.conf_alpha
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

    # ── direct unbind ──────────────────────────────────────────────────
    def _direct_query(self, subject, relation, inverse):
        s = self._ent(subject).astype(np.int32)
        r = self._rel(relation).astype(np.int32)
        if inverse:
            probe = r * self._permute(s).astype(np.int32)
            return self.acc * probe
        else:
            probe = s * r
            return self._unpermute(self.acc * probe)

    def _encode_probe(self, subject, relation, inverse):
        s = self._ent(subject)
        r = self._rel(relation)
        if inverse:
            return (r * self._permute(s)).astype(np.int8)
        return (s * r).astype(np.int8)

    # ── recurrent refinement ───────────────────────────────────────────
    def _recurrent(self, initial_h):
        h = initial_h.copy()
        history = []
        sqrt_dim = float(np.sqrt(self.cfg.dim))
        for i in range(self.cfg.n_loops):
            W = h.reshape(self.cfg.m, self.cfg.n).astype(np.float64)
            norm_W = float(np.linalg.norm(W)) / sqrt_dim
            DeltaS = 1.0 / (1.0 + norm_W)
            packet = self.core.step(
                W, version=self.cfg.packet_version, mu=int(i % 2),
                F_res=float(np.mean(W)), DeltaS=DeltaS)
            W_hat = (packet.Ub @ packet.Vb).astype(np.float64)
            h_c = W_hat.reshape(self.cfg.dim)
            scar = float(np.linalg.norm(packet.Lambda))
            delta = float(np.abs(h - h_c).mean())
            gate = self.sigma.evaluate(
                scar_energy=scar, mu=int(packet.mu),
                volume_ok=bool(packet.volume_ok))
            inputs = AbstentionInputs(
                DeltaS=float(packet.DeltaS), mu=int(packet.mu),
                scar_energy=scar, volume_ok=bool(packet.volume_ok))
            sig_arg = gate.value if gate != SigmaAction.NONE else None
            state = route_signals(inputs, self.thresholds, sig_arg)
            history.append({
                "loop": i, "scar_energy": scar, "delta": delta, "mu": int(packet.mu),
                "DeltaS": float(packet.DeltaS), "rank": int(packet.rank),
                "volume_ok": bool(packet.volume_ok),
                "sigma1_action": gate.value, "gate_state": state,
                "packet_hash": packet.packet_hash[:12],
            })
            if state == CLEANUP:
                h = initial_h.copy()
                continue
            if state == ABSTAIN:
                return h_c, history, "ABSTAIN", state
            if delta < self.cfg.convergence_threshold:
                return h_c, history, "CONVERGED", state
            h = h_c
        return h, history, "MAX_LOOPS", history[-1]["gate_state"]

    # ── quantum sim ────────────────────────────────────────────────────
    def _quantum_sim(self, probe, exclude):
        readout = self._readout()
        cands = []
        for _ in range(self.cfg.quantum_samples):
            mask = self.rng.random(self.cfg.dim) < 0.05
            pert = np.where(mask, -probe, probe).astype(np.int8)
            cands.append((readout * pert).astype(np.int8))
        sup = np.sum(np.stack(cands), axis=0)
        measured = np.where(sup >= 0, 1, -1).astype(np.int8)
        return self._cleanup(measured, exclude)

    # ── ask ────────────────────────────────────────────────────────────
    def _ask(self, subject, relation, inverse):
        if subject not in self.entities:
            return Answer(None, 0.0, "ABSTAINED", "ABSTAIN", 0,
                          reason=f"unknown entity '{subject}'")

        # 1. Direct unbind
        retrieved = self._direct_query(subject, relation, inverse)
        best, conf = self._cleanup(retrieved, exclude={subject})

        # 2. Fast path
        if conf >= self.cfg.classical_conf:
            path = [(best, relation, subject)] if inverse else [(subject, relation, best)]
            return Answer(best, conf, "ACCEPTED", "CLASSICAL", 0, path=path)

        # 3. Recurrent refinement
        probe = self._encode_probe(subject, relation, inverse)
        refined, history, exit_reason, gate_state = self._recurrent(probe)

        if exit_reason == "ABSTAIN":
            return Answer(None, conf, "ABSTAINED", "ABSTAIN", len(history),
                          loop_history=history, gate_state=gate_state,
                          reason="sigma-1 gate routed to ABSTAIN")

        refined_bip = np.where(refined >= 0, 1, -1).astype(np.int32)
        refined_retrieved = self.acc * refined_bip
        if not inverse:
            refined_retrieved = self._unpermute(refined_retrieved)

        best2, conf2 = self._cleanup(refined_retrieved, exclude={subject})
        if conf2 > conf:
            best, conf = best2, conf2

        # 4. Quantum-sim if still below classical
        if conf < self.cfg.classical_conf and conf >= self.cfg.abstention_gate:
            bq, cq = self._quantum_sim(refined, exclude={subject})
            if cq > conf:
                best, conf = bq, cq

        # 5. Abstention gate
        if conf < self.cfg.abstention_gate or best is None:
            return Answer(None, conf, "ABSTAINED", "ABSTAIN", len(history),
                          loop_history=history, gate_state=gate_state,
                          reason=f"confidence {conf:.4f} < gate {self.cfg.abstention_gate}")

        mode = "CLASSICAL" if conf >= self.cfg.classical_conf else "QUANTUM_SIM"
        path = [(best, relation, subject)] if inverse else [(subject, relation, best)]
        return Answer(best, conf, "ACCEPTED", mode, len(history), path=path,
                      loop_history=history, gate_state=gate_state)

    def ask(self, subject, relation):
        return self._ask(subject, relation, inverse=False)

    def ask_inverse(self, obj, relation):
        return self._ask(obj, relation, inverse=True)

    def chain(self, start, relations):
        current, path, conf = start, [], 1.0
        total_loops = 0
        modes = []
        hist_acc = []
        for rel in relations:
            a = self.ask(current, rel)
            total_loops += a.loops
            modes.append(a.mode)
            hist_acc.extend(a.loop_history)
            if a.status == "ABSTAINED":
                return Answer(None, conf, "ABSTAINED", "ABSTAIN", total_loops,
                              path=path, loop_history=hist_acc,
                              reason=f"chain broke at '{current} --{rel}--> ?'")
            path.extend(a.path)
            conf *= a.confidence
            current = a.value
        mode = "QUANTUM_SIM" if "QUANTUM_SIM" in modes else "CLASSICAL"
        return Answer(current, conf, "ACCEPTED", mode, total_loops,
                      path=path, loop_history=hist_acc)

    def analogy(self, a, b, c):
        for n in (a, b, c):
            if n not in self.entities:
                return Answer(None, 0.0, "ABSTAINED", "ABSTAIN", 0,
                              reason=f"unknown entity '{n}'")
        transform = (self._ent(a) * self._ent(b)).astype(np.int8)
        candidate = (self._ent(c) * transform).astype(np.int32)
        best, conf = self._cleanup(candidate, exclude={a, b, c})
        if conf < self.cfg.abstention_gate:
            return Answer(None, conf, "ABSTAINED", "CLASSICAL", 0,
                          reason=f"analogy conf {conf:.4f} below gate")
        return Answer(best, conf, "ACCEPTED", "CLASSICAL", 0,
                      path=[(a, "->", b), (c, "->", best)])

    def explain(self, ans):
        head = f"[{ans.status}] mode={ans.mode} loops={ans.loops} conf={ans.confidence:.4f}"
        if ans.gate_state:
            head += f" gate={ans.gate_state}"
        if ans.status == "ABSTAINED":
            return f"{head}\n  reason: {ans.reason}"
        lines = [head, f"  answer: {ans.value}"]
        for s, r, o in ans.path:
            lines.append(f"    {s} --{r}--> {o}")
        return "\n".join(lines)

    def loop_trace(self, ans):
        if not ans.loop_history:
            return "(no loop history)"
        lines = ["loop | scar | delta | mu | DeltaS | rank | vol | gate", "-" * 68]
        for h in ans.loop_history:
            lines.append(
                f"  {h['loop']:2d} | {h['scar_energy']:.4f} | {h['delta']:.4f} | "
                f"{h['mu']}  | {h['DeltaS']:.4f} | {h['rank']:4d} | "
                f"{'ok' if h['volume_ok'] else 'BAD':>3s} | {h['gate_state']}")
        return "\n".join(lines)

    def stats(self):
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
            "conf_mode": self.cfg.conf_mode,
            "conf_alpha": float(self.cfg.conf_alpha),
        }

    def save(self, path):
        Path(path).write_text(json.dumps({
            "cfg": {**asdict(self.cfg), "seed_list": list(self.cfg.seed_list)},
            "acc": self.acc.tolist(),
            "entities": {k: v.tolist() for k, v in self.entities.items()},
            "relations": {k: v.tolist() for k, v in self.relations.items()},
            "facts": [list(t) for t in self.facts],
            "perm": self._perm.tolist(),
        }))

    @classmethod
    def load(cls, path):
        raw = json.loads(Path(path).read_text())
        cfg = TitanosConfig(**raw["cfg"])
        obj = cls(cfg)
        obj.acc = np.array(raw["acc"], dtype=np.int32)
        obj.entities = {k: np.array(v, dtype=np.int8) for k, v in raw["entities"].items()}
        obj.relations = {k: np.array(v, dtype=np.int8) for k, v in raw["relations"].items()}
        obj.facts = [tuple(t) for t in raw["facts"]]
        obj._perm = np.array(raw["perm"])
        obj._perm_inv = np.argsort(obj._perm)
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


def parse_query(text):
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
