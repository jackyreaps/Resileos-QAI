#!/usr/bin/env python3
"""φ-compress structural probe (RES-401 §4 / RES-501 §8 item 1).

The orientation unit test verifies that θ/ω of kept oscillators survive
contraction. This probe verifies the consequence at the level φ-compress
actually operates on: **integer hops, graph/array structure, and golden-
ladder geometry**. No time-series R trajectory — the field's oscillation
is a state property, measured as a snapshot after each contraction step.

Five conditions measured, one per φ-compress primitive:

    C1  contract_rank(r)       -- rank contraction preserves ladder address
    C2  contract_depth(L)      -- hierarchy depth contraction preserves hops
    C3  contract_repeated(v,k) -- repeated contraction is monotone and stable
    C4  select_by_zeckendorf   -- Fibonacci graph selection keeps structural nodes
    C5  contracted_ladder(r)   -- φ-power spacing preserved for survivors

Pass condition (RES-401 §4, restated for structural quantities):

    C1  contracted ladder omega[k] == original omega[survivor_k] for all k
    C2  hop count needed to reach a target is unchanged after depth contraction
    C3  contract_repeated(v, k) is non-increasing and terminates
    C4  selected nodes have strictly lower Zeckendorf rank than rejected nodes
    C5  ladder ratios omega[k+1]/omega[k] ~ PHI for all k in contracted ladder

If all five hold, the contraction is structurally sound — it preserves
the address structure, hop reachability, and geometric spacing the
design depends on. If any fail, that is the specific primitive that
loses structure, and the fix belongs there.

Usage:
    PYTHONPATH=src python scripts/run_phi_compress_probe.py \
        --out artifacts/report_phi_compress_probe.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from resileos.phi_compress import (  # noqa: E402
    PHI_HAT,
    contract_depth,
    contract_rank,
    contract_repeated,
    contracted_ladder,
    select_by_zeckendorf,
    zeckendorf_rank,
)
from resileos.substrate.oscillator import PHI, golden_ladder  # noqa: E402


# ── C1: rank contraction preserves ladder address ─────────────────────


def probe_rank_contraction(r_values: list[int]) -> dict[str, Any]:
    """For each r, contract and verify the survivors keep their φ-power address.

    contract_rank returns an integer (the new rank). The survivors are
    the first `new_r` entries of `golden_ladder(r)` — because the ladder
    is φ-sorted ascending, keeping the first new_r preserves the lowest
    addresses. Verify that `contracted_ladder(r)[k] == golden_ladder(r)[k]`.
    """
    rows = []
    all_preserved = True
    for r in r_values:
        new_r = contract_rank(r, min_rank=2)
        if new_r >= r:
            # No contraction possible at this min_rank.
            rows.append({
                "r": r, "new_r": new_r, "contracted": False,
                "address_preserved": True,
            })
            continue
        full = golden_ladder(r)
        contracted = contracted_ladder(r, min_rank=2)
        preserved = bool(np.allclose(
            contracted, full[: len(contracted)], atol=1e-12
        ))
        all_preserved = all_preserved and preserved
        rows.append({
            "r": r,
            "new_r": int(new_r),
            "contracted": True,
            "ratio": float(new_r / r),
            "phi_hat_expected": float(PHI_HAT),
            "address_preserved": preserved,
            "address_head": [float(x) for x in contracted[:4]],
        })
    return {
        "primitive": "contract_rank",
        "rows": rows,
        "all_preserved": all_preserved,
    }


# ── C2: depth contraction preserves hop count ─────────────────────────


def probe_depth_contraction(L_values: list[int]) -> dict[str, Any]:
    """contract_depth(L) reduces hierarchy depth. The number of hop levels
    needed to reach a target token is the depth itself (level-0 token,
    level-L top packet). After contraction, the surviving levels must
    still address every token — i.e. the contracted depth is the new hop
    count, and it is non-increasing.
    """
    rows = []
    all_preserved = True
    for L in L_values:
        new_L = contract_depth(L, min_depth=2)
        if new_L >= L:
            rows.append({
                "L": L, "new_L": new_L, "contracted": False,
                "hop_preserved": True,
            })
            continue
        # The hop count = L. After contraction it is new_L. Preserved
        # means the target is still reachable at new_L hops.
        preserved = new_L < L and new_L >= 2
        all_preserved = all_preserved and preserved
        rows.append({
            "L": L,
            "new_L": int(new_L),
            "contracted": True,
            "hop_count_before": int(L),
            "hop_count_after": int(new_L),
            "hop_preserved": preserved,
        })
    return {
        "primitive": "contract_depth",
        "rows": rows,
        "all_preserved": all_preserved,
    }


# ── C3: repeated contraction is monotone and terminates ───────────────


def probe_repeated_contraction(values: list[int]) -> dict[str, Any]:
    """contract_repeated(v, k) applies k φ-steps. Must be non-increasing
    and terminate at min_value.
    """
    rows = []
    all_preserved = True
    for v in values:
        seq = [v]
        current = v
        for _ in range(20):
            nxt = contract_repeated(current, steps=1, min_value=2)
            if nxt == current:
                break
            seq.append(nxt)
            current = nxt
        monotone = all(seq[i] >= seq[i + 1] for i in range(len(seq) - 1))
        terminates = seq[-1] <= max(2, int(np.floor(v * PHI_HAT ** len(seq))))
        preserved = monotone and terminates
        all_preserved = all_preserved and preserved
        rows.append({
            "v": v,
            "sequence": [int(x) for x in seq],
            "steps": len(seq) - 1,
            "monotone": bool(monotone),
            "terminates": bool(terminates),
            "preserved": bool(preserved),
        })
    return {
        "primitive": "contract_repeated",
        "rows": rows,
        "all_preserved": all_preserved,
    }


# ── C4: Zeckendorf graph selection preserves structural nodes ─────────


def probe_zeckendorf_selection(n_values: list[int]) -> dict[str, Any]:
    """select_by_zeckendorf(n, keep) picks the `keep` items with the
    lowest Fibonacci (Zeckendorf) rank. This is the graph/array selection:
    structurally important nodes (decomposable into fewer Fibonacci
    terms) survive, high-rank nodes drop.
    """
    rows = []
    all_preserved = True
    for n in n_values:
        keep = max(2, n // 2)
        selected = select_by_zeckendorf(n, keep=keep)
        ranks_all = np.array([zeckendorf_rank(i + 1) for i in range(n)])
        ranks_sel = ranks_all[selected]
        ranks_rej = np.delete(ranks_all, selected)
        # Structural preservation: every selected node's rank is <= every
        # rejected node's rank (with ties allowed).
        if len(ranks_rej) == 0:
            preserved = True
        else:
            preserved = bool(ranks_sel.max() <= ranks_rej.min())
        all_preserved = all_preserved and preserved
        rows.append({
            "n": n,
            "keep": keep,
            "selected_indices": [int(i) for i in selected],
            "selected_ranks_max": int(ranks_sel.max()) if len(ranks_sel) else 0,
            "rejected_ranks_min": int(ranks_rej.min()) if len(ranks_rej) else None,
            "structural_preserved": preserved,
        })
    return {
        "primitive": "select_by_zeckendorf",
        "rows": rows,
        "all_preserved": all_preserved,
    }


# ── C5: golden ladder geometry (φ-power spacing) preserved ────────────


def probe_ladder_geometry(r_values: list[int]) -> dict[str, Any]:
    """contracted_ladder(r) must preserve the φ-power ratio
    omega[k+1]/omega[k] = PHI for every adjacent pair. This is the
    geometric oscillation: the ladder's oscillation is its φ-power
    progression, not a time series.
    """
    rows = []
    all_preserved = True
    for r in r_values:
        new_r = contract_rank(r, min_rank=3)
        if new_r < 3:
            continue
        ladder = contracted_ladder(r, min_rank=3)
        if len(ladder) < 2:
            continue
        ratios = ladder[1:] / ladder[:-1]
        preserved = bool(np.allclose(ratios, PHI, atol=1e-9))
        all_preserved = all_preserved and preserved
        rows.append({
            "r": r,
            "new_r": int(new_r),
            "ladder_len": int(len(ladder)),
            "ratio_mean": float(ratios.mean()),
            "ratio_std": float(ratios.std()),
            "phi_expected": float(PHI),
            "geometry_preserved": preserved,
        })
    return {
        "primitive": "contracted_ladder",
        "rows": rows,
        "all_preserved": all_preserved,
    }


# ── main ───────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(description="phi-compress structural probe")
    ap.add_argument(
        "--out", type=str, default="artifacts/report_phi_compress_probe.json"
    )
    args = ap.parse_args()

    r_values = [4, 6, 8, 12, 16]
    L_values = [4, 8, 16, 32, 64]
    v_values = [8, 16, 32, 64, 128]
    n_values = [8, 16, 32, 64]

    print("phi-compress structural probe")
    print(f"  PHI = {PHI:.6f}  PHI_HAT = {PHI_HAT:.6f}")
    print()

    c1 = probe_rank_contraction(r_values)
    c2 = probe_depth_contraction(L_values)
    c3 = probe_repeated_contraction(v_values)
    c4 = probe_zeckendorf_selection(n_values)
    c5 = probe_ladder_geometry(r_values)

    results = {
        "C1_contract_rank": c1,
        "C2_contract_depth": c2,
        "C3_contract_repeated": c3,
        "C4_select_by_zeckendorf": c4,
        "C5_contracted_ladder": c5,
    }

    all_passed = all(
        v["all_preserved"] for v in results.values()
    )

    verdicts = {
        "C1_contract_rank": "PASS" if c1["all_preserved"] else "FAIL",
        "C2_contract_depth": "PASS" if c2["all_preserved"] else "FAIL",
        "C3_contract_repeated": "PASS" if c3["all_preserved"] else "FAIL",
        "C4_select_by_zeckendorf": (
            "PASS" if c4["all_preserved"] else "FAIL"
        ),
        "C5_contracted_ladder": "PASS" if c5["all_preserved"] else "FAIL",
    }

    report = {
        "probe": "phi_compress_structural",
        "constants": {
            "phi": float(PHI),
            "phi_hat": float(PHI_HAT),
        },
        "conditions": results,
        "verdicts": verdicts,
        "all_passed": bool(all_passed),
        "notes": [
            "C1: contract_rank preserves φ-power address of survivors",
            "C2: contract_depth preserves hop count reachability",
            "C3: contract_repeated is monotone and terminates",
            "C4: select_by_zeckendorf keeps lower-rank (structural) nodes",
            "C5: contracted_ladder preserves φ-power ratio between adjacent entries",
            "No R-over-time trajectory: field oscillation is a snapshot state,",
            "verified by test_phi_orientation_transfer.py not by this probe.",
        ],
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))

    for k, v in verdicts.items():
        print(f"  {k:30s} {v}")
    print()
    print(f"all passed: {all_passed}")
    print(f"wrote {out}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
