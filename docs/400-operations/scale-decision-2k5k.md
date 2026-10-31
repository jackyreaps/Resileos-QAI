---
doc: RES-400-scale-decision
title: Scale profile decision — 2k / 5k
status: proposed
depends_on: [RES-320, RES-317]
---

# Scale profile decision

## OOM cause (and fix)

Default Titanos uses `dim=10000` attractor memory. A full default learn at N=5000 was killed (exit 137) when:

1. The scale script kept **two** Titanos instances alive (bands-only + default).
2. Attractor kept **float64** copies of every pattern **and** a Hopfield matrix of shape `(N, dim)` (~400MB+ each at N=5k).

**Fixes applied in tree for measurement / stability:**

- Scale path: one instance at a time, `learn_many`, GC between modes.
- Pattern list: **float32** accumulation.
- Hopfield rebuild: **capped at 2048** rows (SDM still records every write; Hopfield is denoise prior, not the fact store).

## Measured

| n_facts | learn attractor off | learn default (after fix) | query hit rate | notes |
|---------|---------------------|---------------------------|----------------|-------|
| 2000 | **0.11 s** | **9.13 s** | **1.0** | prior full default |
| 5000 | **0.17 s** | **13.60 s** | **1.0** | 5000 patterns in SDM; Hopfield ≤2048 |

State size (bands-oriented save earlier): ~35 MB @2k, ~71 MB @5k.

## Recommendations

1. **Bulk seed / hubs:** `learn_many` + deferred attractor; or `use_attractor=False` then one flush.
2. **DiskBandStore:** not required for correctness at 5k (hit rate 1.0). Optional for ops if multi-tenant state size/SLOs demand it.
3. **Small hosts:** do not run dual full-dim attractor profiles; keep Hopfield cap (or raise only with RAM headroom).
4. **Query:** still negligible vs learn.

## Artifacts

- `artifacts/report_scale_profile_2k.json`
- `artifacts/report_scale_profile_5k.json`
