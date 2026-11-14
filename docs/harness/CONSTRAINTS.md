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

## Harness levels

The harness is leveled, like a layered medium: a protected deep layer,
engines in the middle, and a plastic outer layer. The registry is
`LEVELS` in `src/resileos/persona/upgrade_report.py`, and the upgrade
proposer enforces it.

| Level | What lives there | What a proposal may do |
|---|---|---|
| L0 protected substrate | residual core math (`resileos.core`), the Packet schema and `packet_hash` (`resileos.packet`), Zeus approval (`zeus_head`), `require_verified` (`kin.mouth_policy`, `verify`), `residual_consistency` and `verify_on_stop`, the Hades lesson-only rule (`kin.hades`), and what abstain / NO_ROWS / CONFLICT mean | Nothing. Refused outright and never approvable. |
| L1 engines | Kin roles, demi-gods, legions, the cascade router, risk rules, `SeparatedCycle`, budget and scar accounting, ControlPacket policy (`harness.packet`) | Review only, after a held-out eval and admin approval. Never auto-applied. |
| L2 outer matcher | guides, routing thresholds (`confidence_route`), routing heuristics (`chat.router`), lesson extraction (`kin.lesson_store`), telemetry (`run_trace`), UI chips, eval reporting | Only the allowlisted operational params (`OperationalStore`) may auto-apply. Each change is versioned, metric-gated, and auto-reverted. |

- Lookup uses the longest matching prefix. A `module:Symbol` entry can be
  deeper than its module: `zeus_head` is L0 inside the L1
  `harness.separated`. A proposal that names the whole file of a module
  holding an L0 symbol counts as L0. Unlisted modules count as L1.
- An L2 auto change is also reverted when any L0 or L1 coherence metric
  on the held-out suite drops, even if its own metric improved
  (`guard_l2`). The guarded metrics are residual consistency and
  verification rate (L0), and correct abstention and budget efficiency
  (L1). See `docs/400-operations/trace-and-lessons.md`.
