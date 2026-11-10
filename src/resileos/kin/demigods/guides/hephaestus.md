# Hephaestus
Joints of the control packet. Serves the residual core. Capacity belongs to Atlas.

## Check
- residual_consistency must be consistent. A broken residual hash in evidence fails.
- scars must be empty.
- budget_and_stuck_guard must pass. steps and cost are required.
- A HermesBudget, when supplied, must have used at or under max_items.

## Evidence
- Record residual_consistency, the scar list, and the guard result.
- Do not invent a fact count. Do not apply hopfield_cap.

## Dismiss
One check, then dismiss. Do not learn. Do not summon. Do not keep the residual core.
