---
doc: RES-332-metrics
title: Ops Metrics — Tool Honesty and Residual Growth
status: proposed
depends_on: [RES-330, RES-328-router, RES-327-tools]
---

# Ops Metrics

Immediate instrumentation for the growth spine. No external CVI required.

## 1. Definitions

| ID | Name | How to count |
|----|------|----------------|
| M1 | Tool adherence | `# fact turns with tool/structured call first` / `# TOOL_FACT+HUB_RECALL turns` |
| M2 | Invent rate | `# fact assertions after empty/abstain/NONE` / `# such opportunities` |
| M3 | Store hit rate | Correct object on known probe triples |
| M4 | Hub durability | Hub triples present after save/load |
| M5 | Soft-chat leak | SOFT_CHAT turns that assert unbacked empirical facts |
| M6 | Bulk policy | Imports with N≥threshold using `learn_many` |
| M7 | Prior bound | Hopfield rebuild size ≤ `HF_CAP` |
| M8 | Scale admit | Upscale only if M3 + SLO |

## 2. Probe recipe (text, CPU)

1. Fixed probe set: known global triples + one hub user with `prefers`.  
2. Run tool_mouth / router path (no GPU).  
3. Log class, tool used, status, whether mouth invented.  
4. Write `artifacts/report_ops_metrics.json`.

## 3. Targets (initial)

| Metric | Initial target |
|--------|----------------|
| M1 | ≥ 0.95 |
| M2 | 0 |
| M3 | 1.0 on synthetic known set |
| M4 | pass |
| M5 | 0 on labeled soft set |

## 4. Where to hook

- Router decision + tool result status on each turn  
- `derive_frame` / answer status already expose abstain/none  
- Scale profile already exposes M3-related hit rate and learn timings  

## 5. One line

**Measure tool honesty and residual retain before any personality-train or surface port.**
