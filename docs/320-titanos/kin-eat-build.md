---
doc: RES-338-kin-eat
title: Kin Operators and Eat Filter — First Real Build
status: implemented
depends_on: [RES-334-kin, RES-324, RES-337-seed]
---

# Kin Operators and Eat Filter

## What this is

Executable slice of Zeus **kin** + **eat** path:

| Operator | Role | Answers user facts? |
|----------|------|---------------------|
| **Iris** | Observe metrics / agency → `IrisReport` | No |
| **Metis** | `IrisReport` → `MetisPolicy` (mouth/depth flags) | Only `sys:agency` |
| **Hermes** | Rank/truncate provided context under budget | No |
| **Eat** | External claim → accept/reject/abstain → optional learn | N/A (ingest gate) |

Zeus remains the structured answer child. AgencyGroup “eat” of low-fitness children stays in `substrate/agency.py`.

## Filter (Human Medium–aligned, operational)

Without claiming consciousness: the stack **filters** before durable truth:

1. Unstructured prose → **abstain** (not learned)  
2. Forbidden / malformed → **reject**  
3. Well-formed triple → **accept** → `learn` + optional seed `fact_learned`  

That matches product honesty: emotion/narrative can exist upstream; **store truth** only passes the gate.

## Code

`src/resileos/kin/` · `tests/test_kin_eat.py`

## Next

- Register Iris/Metis/Hermes with AgencyGroup weights  
- `POST /api/v1/eat` for Studio / leCore handoff  
- Wire MetisPolicy to mouth enable in answer route  

## Agency alignment
- `KinBundle.cycle` runs Iris→Metis and can mark agency children inactive from policy.
- `register_answer_child` for Zeus; `register_declining_kin` optional snapshot-only kin handlers (always None).
- `http_routes.register_kin_routes` → POST `/api/v1/eat`, `/eat/preview`, `/kin/cycle`.
