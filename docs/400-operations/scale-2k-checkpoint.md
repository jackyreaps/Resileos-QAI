---
doc: RES-406
title: Scale 2k Checkpoint (seed vs restart)
status: draft
depends_on: [RES-317, RES-320]
---

# Scale 2k Checkpoint

dim=10000, n_facts=2000, in-process measurements (sandbox).

| Config | Time | Measures |
|--------|------|----------|
| Attractor on, deferred Hopfield (ship) | ~8–8.5 s seed | Real seed with RES-317 |
| Attractor off | ~0.04 s | Store / bands floor |
| Pre-fix per-learn Hopfield restack | ~61 s | O(n²) bug (fixed) |
| **Load from ~15 MB state** | **~8.3 s** | **Restart cost** (attractor rebuild from facts) |

Restart cost ≈ seed cost: cold start rebuilds the attractor via deferred
SDM writes + one Hopfield flush. Not first-boot-only.

DiskBandStore (RES-320) remains about **state size / band serialization**,
orthogonal to attractor rebuild after bands are in memory.
