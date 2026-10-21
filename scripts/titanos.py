#!/usr/bin/env python3
"""
Titanos — recurrent-depth prototype on the frozen contracts.

Layers:
    storage           one accumulator per relation (band sharding, RES-306)
    abstention        thresholds from sigma_base / sqrt(anisotropy)
    emergent          non-conservative operator driven by real monitors
    CSI               Causal Sandbox Index over each query (RES-305)
    agency            heuristic routing to registered children (RES-307)
    order parameter   Kuramoto R from theta gates confidence (RES-316)

Storage uses MAP triple binding:
    band += s * r * o               (elementwise, bipolar)
    probe = anchor * r
    retrieved = sign(band) * probe  ~= other_slot + crosstalk

MAP binding is symmetric: probe = anchor * r against Σ(s*r*o) returns
Σ(s*o*anchor), which surfaces whichever slot the anchor occupies. For
an entity that appears on both sides of a relation (Cronus is a child
of Uranus and a parent of Zeus), the retrieved vector is a mixture of
both partners and argmax picks by noise. Cleanup is therefore
restricted to the queried slot using the fact list, which is
authoritative for subject/object direction.

Scoring promotes to float64 before the inner products. np.dot on int8
inputs uses an int8 accumulator and silently overflows for dim > 127,
returning wraparound values that have no relation to the true inner
product.

The "quantum" path is a labeled simulation (QUANTUM_SIM).
"""
from __future__ import annotations

import dataclasses
import json
import math
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
from resileos.substrate.sandbox import (
    CSIState, volume_residual, fast_confidence,
)
from resileos.substrate.agency import AgencyGroup, AgencyChild, HandlerFn


@dataclass
class TitanosConfig:
    packet_version: str = "1.0.0"
    dim: int = 10000
    m: int = 100
    n: int = 100
    r: int = 8
    seed: int = 1337
    n_loops: int = 12

    emergent: bool = True
    nc_gamma_max: float = 0.5
    nc_phase_max: float = 0.4
    nc_decay: float = 0.9

    conf_alpha_classical: float = 4.0
    conf_alpha_abstain: float = 1.5
    classical_conf: float | None = None
    abstention_gate: float | None = None

    quantum_samples: int = 16
    convergence_threshold: float = 0.02

    conf_mode: str = "sim"
    conf_alpha: float = 0.6

    sigma_E: float = 10.0
    sigma1_k: int = 3
    sigma_k: int | None = None

    N_warm: int = 512
    E_sat: float = 10.0
    E_sigma: float = 10.0
    tau_sat: float = 0.9
    tau_low: float = 0.1

    csi_window: int = 64
    csi_external_term: bool = True
    csi_living_factor: bool = False
    csi_optimal_drift: float = 0.1
    csi_living_sharpness: float = 4.0
    csi_fast_path: bool = False
    csi_fast_threshold: float = 0.6
    csi_health_threshold: float = 0.5

    use_order_parameter_gate: bool = False
    order_parameter_floor: float = 0.5

    X: float = 70.0
    Y: int = 3
    seed_list: tuple[int, ...] = (0, 1, 2)
    scar_var_floor: float = 0.0
    deltaS_range_floor: float = 0.0
    drift_ratio_floor: float = 0.0

    def __post_init__(self) -> None:
        if self.sigma_k is not None:
            self.sigma1_k = int(self.sigma_k)
        if not (0.0 <= self.order_parameter_floor <= 1.0):
            raise ValueError("order_parameter_floor must be in [0, 1]")

    @classmethod
    def from_json(cls, path) -> "TitanosConfig":
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
    noise_sigma: float = 0.0
    noise_sigma_base: float = 0.0
    anisotropy: float = 1.0
    band_count: int = 0
    emergent: bool = False
    csi: float = 1.0
    fast_confidence: float = 0.0
    fast_path_used: bool = False
    escalated: bool = False
    child_name: str | None = None
    order_parameter: float = 1.0
    raw_confidence: float = 0.0
    order_parameter_scale: float = 1.0


class Titanos:

    def __init__(self, cfg: TitanosConfig):
        self.cfg = cfg
        if cfg.m * cfg.n != cfg.dim:
            raise ValueError(f"m*n ({cfg.m*cfg.n}) != dim ({cfg.dim})")
        self.rng = np.random.default_rng(cfg.seed)
        self.core = ResidualCore(
            CoreConfig(m=cfg.m, n=cfg.n, r=cfg.r),
            seed=cfg.seed,
            non_conservative=bool(cfg.emergent),
            nc_gamma_max=cfg.nc_gamma_max,
            nc_phase_max=cfg.nc_phase_max,
            nc_decay=cfg.nc_decay,
        )
        self._bands: dict[str, np.ndarray] = {}
        self._counts: dict[str, int] = {}
        self._perm = self.rng.permutation(cfg.dim)
        self._perm_cache: dict[int, np.ndarray] = {0: np.arange(cfg.dim)}
        self.entities: dict[str, np.ndarray] = {}
        self.relations: dict[str, np.ndarray] = {}
        self.roles: dict[str, np.ndarray] = {}
        for name in ("S", "O"):
            self.roles[name] = self._bip()
        self.sigma = SigmaGate(E_sigma=cfg.E_sigma, k=cfg.sigma1_k)
        self.thresholds = AbstentionThresholds(
            E_sat=cfg.E_sat, tau_sat=cfg.tau_sat, tau_low=cfg.tau_low)
        self.facts: list = []
        self._query_count = 0
        self._fast_path_count = 0
        self._escalation_count = 0
        self._csi = CSIState(
            window=cfg.csi_window,
            external_term=cfg.csi_external_term,
            living_factor=cfg.csi_living_factor,
            optimal_drift=cfg.csi_optimal_drift,
            living_sharpness=cfg.csi_living_sharpness,
        )
        self.agency = AgencyGroup()

    # ── accumulators ─────────────────────────────────────────────────
    @property
    def acc(self) -> np.ndarray:
        return self._merged_acc()

    def _merged_acc(self) -> np.ndarray:
        if not self._bands:
            return np.zeros(self.cfg.dim, dtype=np.int32)
        return np.sum(
            np.stack(list(self._bands.values())), axis=0).astype(np.int32)

    def _slot_candidates(
        self, relation: str, inverse: bool
    ) -> set[str]:
        """Entities that occupy the queried slot for `relation`.

        The MAP probe `anchor * r` against `Σ(s*r*o)` is symmetric: it
        recovers the anchor's partner whichever slot the anchor occupies.
        For an anchor that appears on both sides of a relation (Cronus is
        both a child of Uranus and a parent of Zeus), the retrieved vector
        is a mixture and argmax picks by noise.

        Restricting cleanup to entities that actually appear in the
        intended slot removes the mixture. The data is already in
        `self.facts`; this is a set lookup, not a VSA operation.

        inverse=False -> objects  (forward: anchor points at them)
        inverse=True  -> subjects (inverse: they point at anchor)
        """
        idx = 0 if inverse else 2
        return {
            f[idx] for f in self.facts if f[1] == relation
        }

    def _get_band(self, relation: str) -> np.ndarray:
        if relation not in self._bands:
            self._bands[relation] = np.zeros(self.cfg.dim, dtype=np.int32)
            self._counts[relation] = 0
        return self._bands[relation]

    # ── monitors ─────────────────────────────────────────────────────
    def _current_anisotropy(self) -> float:
        D = np.asarray(self.core.D)
        if D.size == 0:
            return 1.0
        mags = np.abs(D)
        return float(mags.max() / (mags.min() + 1e-300))

    def _order_parameter(self) -> float:
        op = getattr(self.core, "_nonconservative", None)
        if op is None:
            return 1.0
        theta = np.asarray(op.theta, dtype=np.float64).ravel()
        if theta.size == 0:
            return 1.0
        z = np.exp(1j * theta)
        return float(np.abs(np.mean(z)))

    def _order_parameter_scale(self, R: float) -> float:
        f = self.cfg.order_parameter_floor
        return float(f + (1.0 - f) * R)

    def _noise_sigma_base(self, relation: str) -> float:
        N_r = self._counts.get(relation, 0)
        if N_r < 2:
            return 0.0
        return float(np.sqrt((N_r - 1) / self.cfg.dim))

    def _noise_sigma_effective(self, relation: str) -> float:
        sigma_base = self._noise_sigma_base(relation)
        if not self.cfg.emergent:
            return sigma_base
        a = self._current_anisotropy()
        return float(sigma_base / np.sqrt(max(a, 1.0)))

    def _thresholds_for(self, relation: str) -> tuple[float, float, float]:
        sigma_eff = self._noise_sigma_effective(relation)
        classical = (self.cfg.classical_conf
                     if self.cfg.classical_conf is not None
                     else self.cfg.conf_alpha_classical * sigma_eff)
        abstain = (self.cfg.abstention_gate
                   if self.cfg.abstention_gate is not None
                   else self.cfg.conf_alpha_abstain * sigma_eff)
        return float(classical), float(abstain), float(sigma_eff)

    def _compute_monitors(self, subject: str, relation: str,
                          probe: np.ndarray) -> tuple[float, float, int]:
        acc = self._bands.get(relation)
        if acc is None:
            return 0.0, 0.0, 0
        readout = np.where(acc >= 0, 1, -1).astype(np.int8)
        retrieved = (readout * probe).astype(np.int8)
        scores = self._score_candidates(
            retrieved, acc=acc, exclude={subject})
        if not scores:
            return 0.0, 0.0, 0
        sims = np.array([s for _, s, _ in scores], dtype=np.float64)
        mags = np.array([m for _, _, m in scores], dtype=np.float64)
        total = float(np.abs(sims).sum() + np.abs(mags).sum())
        top = float(np.max(np.abs(sims) + np.abs(mags))) if len(sims) else 0.0
        F_res = (total - top) / total if total > 0 else 0.0
        if len(mags) > 1:
            p = np.exp(np.abs(mags) * 8.0)
            p = p / (p.sum() + 1e-12)
            entropy = float(-np.sum(p * np.log(p + 1e-12)))
            max_entropy = float(np.log(len(p)))
            DeltaS = 1.0 - (entropy / max_entropy) if max_entropy > 0 else 1.0
        else:
            DeltaS = 1.0
        mu = int(np.sum(sims) >= 0.0)
        return float(F_res), float(DeltaS), int(mu)

    # ── learned primitives ───────────────────────────────────────────
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
        """Deprecated: roles are no longer used on the primary path."""
        return (self.roles[role] * self._rel(relation)).astype(np.int8)

    def _readout(self, relation: str | None = None) -> np.ndarray:
        if relation is None:
            acc = self._merged_acc()
        else:
            acc = self._bands.get(relation)
            if acc is None:
                return np.zeros(self.cfg.dim, dtype=np.int8)
        return np.where(acc >= 0, 1, -1).astype(np.int8)

    # ── MAP triple binding ───────────────────────────────────────────
    def learn(self, subject: str, relation: str, obj: str) -> None:
        """
        band += s * r * o  (elementwise, bipolar).

        Forward probe s * r retrieves o. Inverse probe o * r retrieves s.
        Because elementwise bind is self-inverse, the probe is symmetric
        and recovers whichever slot the anchor occupies. Slot restriction
        in `_slot_candidates` + `_cleanup(restrict_to=...)` disambiguates
        the direction.
        """
        s = self._ent(subject)
        r = self._rel(relation)
        o = self._ent(obj)
        band = self._get_band(relation)
        band += (s * r * o).astype(np.int32)
        self._counts[relation] += 1
        self.facts.append((subject, relation, obj))

    def _encode_probe(self, anchor: str, relation: str,
                      inverse: bool = False) -> np.ndarray:
        """
        MAP probe: anchor * relation. Recovers the other slot.

        `inverse` is informational; the probe form is the same. The
        direction is enforced during cleanup via `_slot_candidates`,
        which restricts candidates to subjects (inverse) or objects
        (forward) using `self.facts`.
        """
        return (self._ent(anchor) * self._rel(relation)).astype(np.int8)

    # ── scoring / cleanup ────────────────────────────────────────────
    def _score_candidates(self, vec: np.ndarray,
                          acc: np.ndarray | None = None,
                          exclude: set[str] | None = None,
                          restrict_to: set[str] | None = None,
                          ) -> list[tuple[str, float, float]]:
        """
        Score each candidate entity against a retrieved vector.

        sim = <vec, anchor> / D   (sign-aware, query-specific)
        mag = |<acc, anchor>| / D (accumulator magnitude)

        `restrict_to` limits candidates to the queried slot (subjects
        for inverse, objects for forward). This is what enforces
        direction; the VSA probe alone cannot.

        Both dots are promoted to float64. np.dot on int8 inputs uses
        an int8 accumulator and silently overflows for dim > 127,
        producing wraparound values that have no relation to the true
        inner product. Promoting avoids this.
        """
        exclude = exclude or set()
        D = float(self.cfg.dim)
        if acc is None:
            acc = self._merged_acc()
        vec_f = np.asarray(vec, dtype=np.float64)
        acc_f = np.asarray(acc, dtype=np.float64)
        out: list[tuple[str, float, float]] = []
        for name, anchor in self.entities.items():
            if name in exclude:
                continue
            if restrict_to is not None and i name not in restrict_to in:
                continue
            a = anchor.astype range(np.float64)
            sim = float(np.dot(self(vec_f, a)) / D
            mag = abs(float(np.dot(acc_f, a))) / D
            out.append((name, sim, mag))
        return out

    def _cleanup(self, vec: np.ndarray,
                 acc: np.ndarray | None = None,
                 exclude: set[str] | None = None,
                 mode: str | None = None,
                 restrict_to: set[str] | None = None,
                 ) -> tuple[str | None, float]:
        scores = self._score_candidates(
            vec, acc=acc, exclude=exclude, restrict_to=restrict_to)
        if not scores:
            return None, 0.0
        names = [n for n, _, _ in scores]
        s = np.array([x[1] for x in scores])
        m = np.array([x[2] for x in scores])
        mode = mode or self.cfg.conf_mode
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
            conf.c = alpha * (fgs / smax) + (1.0 - alpha) * (m / mmax)
        else:
            raise ValueError(f"unknown conf_mode: {mode}")
        idx = int(np.argmax(conf))
        return names[idx], float(conf[idx])

    # ── recurrent loop ───────────────────────────────────────────────
    def _recurrent(self, initial_h: np.ndarray,
                   F_res: float = 0.0, DeltaS: float = 0.5, mu: int = 0):
        h = initial_h.copy()
        history: list = []
        sqrt_dim = float(np.sqrt(self.cfg.dim))
        for.n_loops):
            W = h.reshape(self.cfg.m, self.cfg.n).astype(np.float64)
            norm_W = float(np.linalg.norm(W)) / sqrt_dim
            DeltaS_local = 0.5 * DeltaS + 0.5 * (1.0 / (1.0 + norm_W))
            packet = self.core.step(
                W, version=self.cfg.packet_version, mu=int(mu),
                F_res=float(F_res), DeltaS=float(DeltaS_local))
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
                "loop": i, "scar_energy": scar, "delta": delta,
                "mu": int(packet.mu), "DeltaS": float(packet.DeltaS),
                "rank": int(packet.rank),
                "volume_ok": bool(packet.volume_ok),
                "sigma1_action": gate.value, "gate_state": state,
                "packet_hash": packet.packet_hash[:12],
                "volume_residual": volume_residual(packet.volume),
                "anisotropy": self._current_anisotropy(),
                "order_parameter": self._order_parameter(),
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

    def _quantum_sim(self, probe: np.ndarray, acc: np.ndarray,
                     exclude: set[str],
                     restrict_to: set[str] | None = None):
        readout = np.where(acc >= 0, 1, -1).astype(np.int8)
        cands = []
        for _ in range(self.cfg.quantum_samples):
            mask = self.rng.random(self.cfg.dim) < 0.05
            pert = np.where(mask, -probe, probe).astype(np.int8)
            cands.append((readout * pert).astype(np.int8))
        sup = np.sum(np.stack(cands), axis=0)
        measured = np.where(sup >= 0, 1, -1).astype(np.int8)
        return self._cleanup(
            measured, acc=acc, exclude=exclude, restrict_to=restrict_to)

    def _update_csi_from_history(self, history: list) -> None:
        if not history:
            return
        prev = None
        for h in history:
            v = float(h.get("volume_residual", 0.0))
            if prev is None:
                e_int = 0.0
            else:
                e_int = (abs(h["scar_energy"] - prev[0])
                         + abs(h["delta"] - prev[1]))
            self._csi.update(v, e_int)
            prev = (h["scar_energy"], h["delta"])

    # ── single query ─────────────────────────────────────────────────
    def _ask(self, subject: str, relation: str, inverse: bool,
             conf_mode_override: str | None = None) -> Answer:
        if subject not in self.entities:
            return Answer(None, 0.0, "ABSTAINED", "ABSTAIN", 0,
                          reason=f"unknown entity '{subject}'",
                          emergent=self.cfg.emergent,
                          csi=self._csi.value(),
                          order_parameter=self._order_parameter())
        acc = self._bands.get(relation)
        if acc is None or self._counts.get(relation, 0) == 0:
            return Answer(None, 0.0, "ABSTAINED", "ABSTAIN", 0,
                          reason=f"no facts stored for relation '{relation}'",
                          emergent=self.cfg.emergent,
                          csi=self._csi.value(),
                          order_parameter=self._order_parameter())

        self._query_count += 1
        probe = self._encode_probe(subject, relation, inverse=inverse)
        slot = self._slot_candidates(relation, inverse=inverse)
        current_csi = self._csi.value()
        classical_thresh, abstain_thresh, sigma_eff = \
            self._thresholds_for(relation)
        sigma_base = self._noise_sigma_base(relation)
        anisotropy = self._current_anisotropy()
        R = self._order_parameter()
        scale = (self._order_parameter_scale(R)
                 if self.cfg.use_order_parameter_gate else 1.0)

        readout = self._readout(relation)
        direct = (readout * probe).astype(np.int8)
        fast_best, fast_conf = self._cleanup(
            direct, acc=acc, exclude={subject},
            mode=conf_mode_override, restrict_to=slot)
        fast_conf_gated = fast_conf * scale
        fast_conf_blend = fast_confidence(
            fast_conf_gated, sigma_eff, current_csi)

        if (self.cfg.csi_fast_path
                and fast_best is not None
                and fast_conf_gated >= classical_thresh
                and fast_conf_blend >= self.cfg.csi_fast_threshold
                and current_csi >= self.cfg.csi_health_threshold):
            self._fast_path_count += 1
            path = ([(fast_best, relation, subject)] if inverse
                    else [(subject, relation, fast_best)])
            return Answer(fast_best, fast_conf_gated, "ACCEPTED", "FAST",
                          0, path=path,
                          noise_sigma=sigma_eff,
                          noise_sigma_base=sigma_base,
                          anisotropy=anisotropy,
                          band_count=self._counts.get(relation, 0),
                          emergent=self.cfg.emergent,
                          csi=current_csi,
                          fast_confidence=fast_conf_blend,
                          fast_path_used=True, escalated=False,
                          order_parameter=R,
                          raw_confidence=fast_conf,
                          order_parameter_scale=scale)

        if self.cfg.csi_fast_path:
            self._escalation_count += 1

        F_res, DeltaS, mu = self._compute_monitors(subject, relation, probe)
        refined, history, exit_reason, gate_state = self._recurrent(
            probe, F_res=F_res, DeltaS=DeltaS, mu=mu)
        self._update_csi_from_history(history)
        updated_csi = self._csi.value()

        if exit_reason == "ABSTAIN":
            return Answer(None, 0.0, "ABSTAINED", "ABSTAIN", len(history),
                          loop_history=history, gate_state=gate_state,
                          noise_sigma=sigma_eff,
                          noise_sigma_base=sigma_base,
                          anisotropy=anisotropy,
                          band_count=self._counts.get(relation, 0),
                          emergent=self.cfg.emergent,
                          csi=updated_csi,
                          fast_confidence=fast_conf_blend,
                          fast_path_used=False, escalated=True,
                          order_parameter=R,
                          raw_confidence=fast_conf,
                          order_parameter_scale=scale,
                          reason="sigma-1 gate routed to ABSTAIN")

        readout2 = self._readout(relation)
        retrieved = (readout2 * probe).astype(np.int8)
        best, raw_conf = self._cleanup(
            retrieved, acc=acc, exclude={subject},
            mode=conf_mode_override, restrict_to=slot)
        conf = raw_conf * scale

        if conf >= classical_thresh:
            mode = "CLASSICAL"
        elif conf >= abstain_thresh:
            best_q, conf_q = self._quantum_sim(
                probe, acc, exclude={subject}, restrict_to=slot)
            if conf_q > conf:
                best, conf = best_q, conf_q
            mode = "QUANTUM_SIM"
        else:
            return Answer(None, conf, "ABSTAINED", "ABSTAIN", len(history),
                          loop_history=history, gate_state=gate_state,
                          noise_sigma=sigma_eff,
                          noise_sigma_base=sigma_base,
                          anisotropy=anisotropy,
                          band_count=self._counts.get(relation, 0),
                          emergent=self.cfg.emergent,
                          csi=updated_csi,
                          fast_confidence=fast_conf_blend,
                          fast_path_used=False, escalated=True,
                          order_parameter=R,
                          raw_confidence=raw_conf,
                          order_parameter_scale=scale,
                          reason=(f"gated confidence {conf:.4f} < abstain "
                                  f"{abstain_thresh:.4f}"))

        if best is None or conf < abstain_thresh:
            return Answer(None, conf, "ABSTAINED", mode, len(history),
                          loop_history=history, gate_state=gate_state,
                          noise_sigma=sigma_eff,
                          noise_sigma_base=sigma_base,
                          anisotropy=anisotropy,
                          band_count=self._counts.get(relation, 0),
                          emergent=self.cfg.emergent,
                          csi=updated_csi,
                          fast_confidence=fast_conf_blend,
                          fast_path_used=False, escalated=True,
                          order_parameter=R,
                          raw_confidence=raw_conf,
                          order_parameter_scale=scale,
                          reason=f"post-quantum gated conf {conf:.4f} "
                                 f"< {abstain_thresh:.4f}")

        path = ([(best, relation, subject)] if inverse
                else [(subject, relation, best)])
        return Answer(best, conf, "ACCEPTED", mode, len(history),
                      path=path, loop_history=history, gate_state=gate_state,
                      noise_sigma=sigma_eff, noise_sigma_base=sigma_base,
                      anisotropy=anisotropy,
                      band_count=self._counts.get(relation, 0),
                      emergent=self.cfg.emergent,
                      csi=updated_csi,
                      fast_confidence=fast_conf_blend,
                      fast_path_used=False, escalated=True,
                      order_parameter=R,
                      raw_confidence=raw_conf,
                      order_parameter_scale=scale)

    def ask(self, subject: str, relation: str) -> Answer:
        return self._ask(subject, relation, inverse=False)

    def ask_inverse(self, obj: str, relation: str) -> Answer:
        return self._ask(obj, relation, inverse=True)

    def iter_entities(self) -> list[str]:
        """All entity names, for full-scan queries (RES-322 §5).

        Enables the query executor to answer clauses whose anchor is an
        unbound variable, e.g. `SELECT ?s, ?o WHERE ?s --knows--> ?o`.
        """
        return list(self.entities.keys())

    # ── agency layer ─────────────────────────────────────────────────
    def register_child(self, name: str, handler: HandlerFn,
                       weight: float = 1.0) -> AgencyChild:
        return self.agency.add_child(name, handler, weight=weight)

    def dispatch(self, subject: str, relation: str,
                 inverse: bool = False,
                 handler_name: str | None = None) -> Answer:
        child: AgencyChild | None = None
        if handler_name is not None:
            child = self.agency.children.get(handler_name)
            if child is not None and not child.active:
                child = None
        else:
            child = self.agency.select()

        if child is None:
            return self._ask(subject, relation, inverse=inverse)

        try:
            ans = child.handler(self, subject, relation, inverse)
        except Exception:
            ans = None

        if ans is None:
            fallback = self._ask(subject, relation, inverse=inverse)
            self.agency.record(child.name, csi=fallback.csi,
                               accepted=(fallback.status == "ACCEPTED"))
            fallback.child_name = child.name
            return fallback

        self.agency.record(child.name, csi=ans.csi,
                           accepted=(ans.status == "ACCEPTED"))
        ans.child_name = child.name
        return ans

    def prune(self) -> list[str]:
        return self.agency.evaluate_and_prune()

    # ── chain / analogy ──────────────────────────────────────────────
    def chain(self, start: str, relations: list[str]) -> Answer:
        current, path, conf = start, [], 1.0
        total_loops = 0
        modes: list[str] = []
        hist_acc: list = []
        for rel in relations:
            a = self.ask(current, rel)
            total_loops += a.loops
            modes.append(a.mode)
            hist_acc.extend(a.loop_history)
            if a.status == "ABSTAINED":
                return Answer(None, conf, "ABSTAINED", "ABSTAIN", total_loops,
                              path=path, loop_history=hist_acc,
                              emergent=self.cfg.emergent,
                              csi=self._csi.value(),
                              order_parameter=self._order_parameter(),
                              reason=(f"chain broke at '{current} --{rel}--> ?'"))
            path.extend(a.path)
            conf *= a.confidence
            current = a.value
        mode = "QUANTUM_SIM" if "QUANTUM_SIM" in modes else "CLASSICAL"
        return Answer(current, conf, "ACCEPTED", mode, total_loops,
                      path=path, loop_history=hist_acc,
                      emergent=self.cfg.emergent,
                      csi=self._csi.value(),
                      order_parameter=self._order_parameter())

    def analogy(self, a: str, b: str, c: str) -> Answer:
        for n in (a, b, c):
            if n not in self.entities:
                return Answer(None, 0.0, "ABSTAINED", "ABSTAIN", 0,
                              reason=f"unknown entity '{n}'",
                              emergent=self.cfg.emergent,
                              csi=self._csi.value(),
                              order_parameter=self._order_parameter())
        transform = (self._ent(a) * self._ent(b)).astype(np.int8)
        candidate = (self._ent(c) * transform).astype(np.int32)
        best, raw_conf = self._cleanup(candidate, acc=self._merged_acc(),
                                       exclude={a, b, c})
        total = sum(self._counts.values())
        sigma = float(np.sqrt(max(total - 1, 0) / self.cfg.dim))
        R = self._order_parameter()
        scale = (self._order_parameter_scale(R)
                 if self.cfg.use_order_parameter_gate else 1.0)
        conf = raw_conf * scale
        abstain = (self.cfg.abstention_gate
                   if self.cfg.abstention_gate is not None
                   else self.cfg.conf_alpha_abstain * sigma)
        if conf < abstain:
            return Answer(None, conf, "ABSTAINED", "CLASSICAL", 0,
                          noise_sigma=sigma, emergent=self.cfg.emergent,
                          csi=self._csi.value(),
                          order_parameter=R,
                          raw_confidence=raw_conf,
                          order_parameter_scale=scale,
                          reason=f"analogy conf {conf:.4f} < {abstain:.4f}")
        return Answer(best, conf, "ACCEPTED", "CLASSICAL", 0,
                      path=[(a, "->", b), (c, "->", best)],
                      noise_sigma=sigma, emergent=self.cfg.emergent,
                      csi=self._csi.value(),
                      order_parameter=R,
                      raw_confidence=raw_conf,
                      order_parameter_scale=scale)

    # ── introspection ────────────────────────────────────────────────
    def explain(self, ans: Answer) -> str:
        head = (f"[{ans.status}] mode={ans.mode} loops={ans.loops} "
                f"conf={ans.confidence:.4f} csi={ans.csi:.4f}")
        if ans.child_name:
            head += f" child={ans.child_name}"
        if ans.fast_path_used:
            head += f" fast_conf={ans.fast_confidence:.4f}"
        if self.cfg.use_order_parameter_gate and ans.order_parameter_scale != 1.0:
            head += (f" R={ans.order_parameter:.3f} "
                     f"scale={ans.order_parameter_scale:.3f}")
        if ans.emergent:
            head += (f" sigma_eff={ans.noise_sigma:.4f} "
                     f"aniso={ans.anisotropy:.3f}")
        if ans.status == "ABSTAINED":
            return f"{head}\n  reason: {ans.reason}"
        lines = [head, f"  answer: {ans.value}"]
        for s, r, o in ans.path:
            lines.append(f"    {s} --{r}--> {o}")
        return "\n".join(lines)

    def loop_trace(self, ans: Answer) -> str:
        if not ans.loop_history:
            return "(no loop history)"
        lines = ["loop | scar | delta | mu | DeltaS | rank | vol | v_t | R | gate",
                 "-" * 84]
        for h in ans.loop_history:
            lines.append(
                f"  {h['loop']:2d} | {h['scar_energy']:.4f} | "
                f"{h['delta']:.4f} | {h['mu']}  | {h['DeltaS']:.4f} | "
                f"{h['rank']:4d} | "
                f"{'ok' if h['volume_ok'] else 'BAD':>3s} | "
                f"{h.get('volume_residual', 0.0):.4f} | "
                f"{h.get('order_parameter', 1.0):.3f} | {h['gate_state']}")
        return "\n".join(lines)

    def stats(self) -> dict:
        total_energy = 0
        for band in self._bands.values():
            total_energy += int(np.sum(band.astype(np.int64) ** 2))
        per_band = {}
        for rel, n in self._counts.items():
            sigma_base = float(np.sqrt(max(n - 1, 0) / self.cfg.dim))
            sigma_eff = self._noise_sigma_effective(rel)
            classical, abstain, _ = self._thresholds_for(rel)
            per_band[rel] = {
                "count": int(n),
                "sigma_base": sigma_base,
                "sigma_eff": sigma_eff,
                "classical_threshold": float(classical),
                "abstain_threshold": float(abstain),
            }
        return {
            "dim": self.cfg.dim,
            "core_matrix": f"{self.cfg.m}x{self.cfg.n}",
            "latent_rank": self.cfg.r,
            "max_loops": self.cfg.n_loops,
            "facts": len(self.facts),
            "entities": len(self.entities),
            "relations": len(self.relations),
            "bands": len(self._bands),
            "accumulator_energy": total_energy,
            "packet_version": self.cfg.packet_version,
            "conf_mode": self.cfg.conf_mode,
            "conf_alpha": float(self.cfg.conf_alpha),
            "emergent": bool(self.cfg.emergent),
            "anisotropy": self._current_anisotropy(),
            "order_parameter": self._order_parameter(),
            "use_order_parameter_gate": bool(self.cfg.use_order_parameter_gate),
            "order_parameter_floor": float(self.cfg.order_parameter_floor),
            "query_count": int(self._query_count),
            "fast_path_count": int(self._fast_path_count),
            "escalation_count": int(self._escalation_count),
            "csi": self._csi.value(),
            "csi_samples": self._csi.samples(),
            "csi_fast_path_enabled": bool(self.cfg.csi_fast_path),
            "agency": self.agency.snapshot(),
            "per_band": per_band,
        }

    # ── persistence ──────────────────────────────────────────────────
    def save(self, path) -> None:
        Path(path).write_text(json.dumps({
            "cfg": {**asdict(self.cfg), "seed_list": list(self.cfg.seed_list)},
            "bands": {k: v.tolist() for k, v in self._bands.items()},
            "counts": dict(self._counts),
            "entities": {k: v.tolist() for k, v in self.entities.items()},
            "relations": {k: v.tolist() for k, v in self.relations.items()},
            "roles": {k: v.tolist() for k, v in self.roles.items()},
            "facts": [list(t) for t in self.facts],
            "perm": self._perm.tolist(),
            "query_count": int(self._query_count),
            "fast_path_count": int(self._fast_path_count),
            "escalation_count": int(self._escalation_count),
            "nc_state": self.core._nonconservative.state_dict(),
            "csi_state": self._csi.state_dict(),
            "agency_state": {
                "weights": {n: c.weight for n, c in self.agency.children.items()},
                "active": {n: c.active for n, c in self.agency.children.items()},
                "eaten": list(self.agency.eaten),
            },
        }))

    @classmethod
    def load(cls, path) -> "Titanos":
        raw = json.loads(Path(path).read_text())
        cfg = TitanosConfig(**raw["cfg"])
        obj = cls(cfg)
        if "bands" in raw:
            obj._bands = {k: np.array(v, dtype=np.int32)
                          for k, v in raw["bands"].items()}
            obj._counts = dict(raw.get("counts", {}))
        elif "acc" in raw:
            obj._bands = {"_legacy": np.array(raw["acc"], dtype=np.int32)}
            obj._counts = {"_legacy": 1}
        obj.entities = {k: np.array(v, dtype=np.int8)
                        for k, v in raw["entities"].items()}
        obj.relations = {k: np.array(v, dtype=np.int8)
                         for k, v in raw["relations"].items()}
        obj.roles = {k: np.array(v, dtype=np.int8)
                     for k, v in raw["roles"].items()}
        obj.facts = [tuple(t) for t in raw["facts"]]
        obj._perm = np.array(raw["perm"])
        obj._perm_cache = {0: np.arange(cfg.dim)}
        obj._query_count = int(raw.get("query_count", 0))
        obj._fast_path_count = int(raw.get("fast_path_count", 0))
        obj._escalation_count = int(raw.get("escalation_count", 0))
        if "nc_state" in raw:
            obj.core._nonconservative.load_state_dict(raw["nc_state"])
        if "csi_state" in raw:
            obj._csi.load_state_dict(raw["csi_state"])
        return obj


# ── thin NLP front-end ─────────────────────────────────────────────────
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


def parse_query(text: str):
    for pat, build in _PATTERNS:
        m = pat.search(text.strip())
        if m:
            return build(m)
    return None


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=None)
    p.add_argument("--conservative", action="store_true")
    p.add_argument("--csi-fast-path", action="store_true")
    p.add_argument("--order-parameter-gate", action="store_true")
    args = p.parse_args()

    cfg = (TitanosConfig.from_json(args.config)
           if args.config else TitanosConfig())
    if args.conservative:
        cfg.emergent = False
    if args.csi_fast_path:
        cfg.csi_fast_path = True
    if args.order_parameter_gate:
        cfg.use_order_parameter_gate = True

    titan = Titanos(cfg)
    print(f"emergent = {cfg.emergent}  "
          f"csi_fast_path = {cfg.csi_fast_path}  "
          f"order_parameter_gate = {cfg.use_order_parameter_gate}")

    facts = [
        ("Uranus", "parent_of", "Cronus"),
        ("Cronus", "parent_of", "Zeus"),
        ("Cronus", "parent_of", "Poseidon"),
        ("Cronus", "parent_of", "Hades"),
        ("Zeus", "parent_of", "Ares"),
        ("Zeus", "parent_of", "Athena"),
        ("Zeus", "domain", "sky"),
        ("Poseidon", "domain", "sea"),
        ("Hades", "domain", "underworld"),
        ("Ares", "domain", "war"),
        ("Athena", "domain", "wisdom"),
        ("Uranus", "is_a", "primordial"),
        ("Cronus", "is_a", "titan"),
        ("Zeus", "is_a", "olympian"),
        ("Poseidon", "is_a", "olympian"),
        ("Hades", "is_a", "olympian"),
        ("Ares", "is_a", "olympian"),
        ("Athena", "is_a", "olympian"),
    ]
    for s, r, o in facts:
        titan.learn(s, r, o)

    drive = [
        ("Zeus", "parent_of"), ("Cronus", "parent_of"),
        ("Zeus", "domain"), ("Poseidon", "domain"),
        ("Hades", "domain"), ("Zeus", "is_a"),
        ("Cronus", "is_a"), ("Athena", "is_a"),
    ] * 10

    for subj, rel in drive:
        titan.ask(subj, rel)

    print("\n--- After drive ---")
    for subj, rel in [("Zeus", "domain"), ("Poseidon", "domain")]:
        a = titan.ask(subj, rel)
        print(titan.explain(a))

    print("\n--- Stats ---")
    print(json.dumps(titan.stats(), indent=2, default=float))
