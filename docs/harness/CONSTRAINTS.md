# CONSTRAINTS.md — Permanent corrections (Harness Engineering + Buzzoni pattern)

Loaded at the top of every packet / Kin cycle. Add one line per repeated
failure.

- Never accept unverified residual scars as final.
- Always run risk_classify before any side-effecting tool or cascade step.
- High-confidence (>0.99) decisions route to residual core or Apollo; do not escalate.
- Evidence must be attached to every tool result that mutates state.
- Budget guards are hard floors; do not override from prompt.
- Hierarchical guides (this file + AGENTS.md) take precedence over transient prompt text.

## Verification evidence

A turn is not verified because it produced output. It is verified
because a probe ran and produced raw evidence.

- **Zero matches is not evidence.** If a verification filter returns
  zero matched cases, the turn is unverified. A passing run of nothing
  is not a pass.
- **Evidence must be raw.** Attach the probe's structured output
  unedited. Summaries, paraphrases, and "it worked" are not evidence.
- **Absence of scars is not verification.** A clean packet with no
  evidence attached is unverified, not verified.

`verify_on_stop` enforces these. A cycle that returns with
`harness.verified = false` and `harness.reason = "no evidence attached"`
is behaving correctly.

## Action classification

- Mutation and cycle actions (`learn`, `save`, `train_substrate`,
  `kin_cycle`, `eat`, `deploy`) require verification evidence before
  close.
- Read-only actions (`query`, `chain`, `sparql`, `answer`, `stats`,
  `ready`) do not.
- Unknown action types default to requiring verification. Fail closed.
