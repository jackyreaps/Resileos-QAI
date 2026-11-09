# CONSTRAINTS.md — Permanent corrections (Harness Engineering + Buzzoni pattern)
# Loaded at the top of every packet / Kin cycle. Add one line per repeated failure.

- Never accept unverified residual scars as final.
- Always run risk_classify before any side-effecting tool or cascade step.
- High-confidence (>0.99) decisions route to residual core or Apollo; do not escalate.
- Evidence must be attached to every tool result that mutates state.
- Budget guards are hard floors; do not override from prompt.
- Hierarchical guides (this file + AGENTS.md) take precedence over transient prompt text.
