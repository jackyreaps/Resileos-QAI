---
doc: RES-344-equal-budget
title: Equal-budget Kin path vs one residual call
status: measured
depends_on: [RES-343-demigods, RES-332]
---

# Equal budget: hierarchy path vs one residual call

Both paths answer the same 22 tasks with the same step budget of 8. The residual path is one store lookup plus `apollo_success`. The hierarchy path spends steps on a Kin cycle, Hephaestus, Atlas, Momus, and a Hades checkpoint, then returns the same lookup. Momus checks that the lookup's own `status` matches an explicit requirement. The extra checks can abstain. They cannot invent a fact the store does not hold.

## How to run

```bash
PYTHONPATH=src:scripts python scripts/bench/equal_budget.py
```

Facts are `configs/titanos-facts.json` (the 14 single-valued `domain` rows). Unknown pairs are absent from that file. Temporal tasks use the windows in `scripts/run_temporal_probe.py`: `obj_A` from 1800-01-01 until 1900-01-01, `obj_B` from 1850-01-01 with no end. Overlap (1860-01-01) and a date before both windows (1750-01-01) must abstain. A single valid object must be returned. A wrong object is a false accept.

Run on 2026-11-10 from this tree, budget 8, 22 tasks (14 known, 4 unknown, 4 temporal).

## Results

| Metric | Residual / Apollo | Kin + Demi-gods + Hades |
|---|---:|---:|
| Accuracy | 1.0 (22/22) | 1.0 (22/22) |
| Correct-abstain rate | 1.0 (6/6) | 1.0 (6/6) |
| False accepts | 0 | 0 |
| False-accept rate | 0.0 | 0.0 |
| Steps, mean | 1.0 | 6.0 |
| Steps, max | 1 | 6 |
| Steps, total | 22 | 132 |
| Latency, mean | 0.361 ms | 43.230 ms |
| Latency, total | 7.949 ms | 951.064 ms |

Accuracy delta (hierarchy minus residual): 0.0. False-accept delta: 0.

## What this does and does not say

On this fixture the hierarchy buys nothing. Both paths are correct, and both refuse the six cases that should abstain. The hierarchy spends the shared budget: 6 steps against 1, and about 120 times the mean latency on this machine. Latency will move from run to run. The step counts will not, unless the path changes.

This is not a claim about prose, planning, or tasks where a second check can catch a bad artefact. Here the artefact is the lookup. Momus is agreeing with that lookup, not with a second source. A tighter budget than 6 steps would stop the hierarchy before Hades and force an abstain, which would lower its accuracy. That case was not the recorded run. Budget 0 does abstain on both paths; the unit test covers it.

## Rerun, 2026-11-12

Same 22 tasks and budget 8, on a cursor cloud agent VM. Both paths were again 22/22 with 0 false accepts. Mean steps stayed 1.0 and 6.0. Mean latency on that VM was 0.388 ms and 32.821 ms. The hierarchy cycle reported residual consistency true on 22/22 and `verified` true on 0/22. The harness reason on every cycle was `no evidence attached`. The call does not pass a residual packet, and `kin_cycle` requires evidence before `verified` is true. False accepts stayed 0. Artifact: `landing/artifacts/report_equal_budget_2026-11-12.json`. The 2026-11-10 table above is a different machine.
