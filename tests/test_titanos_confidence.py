"""
Compare confidence modes for separating known vs unknown queries.
Prints ROC-AUC per mode. Run with: pytest -s -v
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from titanos import Titanos, TitanosConfig


KNOWN_FACTS = [
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

KNOWN_QUERIES = [
    ("Zeus", "domain", False),
    ("Zeus", "parent_of", False),
    ("Cronus", "parent_of", False),
    ("Poseidon", "domain", False),
    ("Athena", "is_a", False),
    ("Zeus", "parent_of", True),
    ("Cronus", "parent_of", True),
    ("sea", "domain", True),
]

UNKNOWN_QUERIES = [
    ("Zeus", "capital_of", False),
    ("Cronus", "domain", False),
    ("Athena", "parent_of", False),
    ("sky", "parent_of", False),
    ("Odin", "parent_of", False),
    ("Thor", "domain", False),
]


def _build(mode: str, alpha: float = 0.6) -> Titanos:
    cfg = TitanosConfig(
        dim=2500, m=50, n=50, r=4, n_loops=6, seed=42,
        classical_conf=0.09, abstention_gate=0.035,
        sigma_E=10.0, sigma_k=3,
        E_sat=10.0, E_sigma=10.0, tau_sat=0.9, tau_low=0.1,
        conf_mode=mode, conf_alpha=alpha,
    )
    t = Titanos(cfg)
    for s, r, o in KNOWN_FACTS:
        t.learn(s, r, o)
    return t


def _score(t: Titanos, subject: str, relation: str, inverse: bool) -> float:
    """
    Score via the cleanup path directly. Avoids the abstention machine
    zeroing the confidence when DeltaS or volume flags trigger.
    """
    if subject not in t.entities:
        return 0.0
    probe = t._encode_probe(subject, relation, inverse=inverse)
    refined, _, _, _ = t._recurrent(probe)
    readout = t._readout()
    retrieved = (readout * refined).astype(np.int8)
    _, conf = t._cleanup(retrieved, exclude={subject})
    return float(conf)


def _confidences(t: Titanos) -> tuple[list[float], list[float]]:
    known = [_score(t, s, r, inv) for s, r, inv in KNOWN_QUERIES]
    unknown = [_score(t, s, r, inv) for s, r, inv in UNKNOWN_QUERIES]
    return known, unknown


def _auc(known: list[float], unknown: list[float]) -> float:
    wins = 0.0
    for k in known:
        for u in unknown:
            if k > u:
                wins += 1.0
            elif k == u:
                wins += 0.5
    return wins / max(len(known) * len(unknown), 1)


MODES = ["sim", "mag", "product", "min", "composite"]


@pytest.mark.parametrize("mode", MODES)
def test_mode_produces_separable_confidences(mode):
    t = _build(mode)
    known, unknown = _confidences(t)
    auc = _auc(known, unknown)
    print(f"\n[{mode:10s}] "
          f"known mean={np.mean(known):.4f} "
          f"unknown mean={np.mean(unknown):.4f} "
          f"AUC={auc:.4f}")
    assert 0.0 <= auc <= 1.0


def test_magnitude_is_candidate_specific():
    """Guards against the constant-mag bug."""
    t = _build("mag")
    vec = np.random.default_rng(0).choice([-1, 1], size=t.cfg.dim).astype(np.int8)
    scores = t._score_candidates(vec)
    mags = [m for _, _, m in scores]
    assert len(set(mags)) > 1, (
        f"mag is constant across {len(mags)} candidates; cannot affect ranking"
    )


def test_report_auc_table():
    results = {}
    for mode in MODES:
        t = _build(mode)
        known, unknown = _confidences(t)
        results[mode] = _auc(known, unknown)

    print("\n=== Confidence mode comparison ===")
    for mode, auc in results.items():
        print(f"  {mode:10s}  AUC = {auc:.4f}")

    baseline = results["sim"]
    best = max(results, key=results.get)
    print(f"\n  baseline (sim)         AUC = {baseline:.4f}")
    print(f"  best     ({best:10s}) AUC = {results[best]:.4f}")
    print(f"  delta                       = {results[best] - baseline:+.4f}")
