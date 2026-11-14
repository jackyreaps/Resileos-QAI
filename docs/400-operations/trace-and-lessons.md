# Run traces, replay, and lesson memory

All of this sits **outside the residual loop**. Nothing here calls `learn`,
touches scars, or feeds back into a decision. Eat stays the only writer.

## One trace per run
`resileos/run_trace.py`. `start_run(task)` opens a run id (context var).
While it is open, these append one JSONL record each to `RESILEOS_RUN_TRACE`
(default `data/run_trace.jsonl`):

| kind | from | fields |
|---|---|---|
| packet | `ControlPacket.append` | event name, turn, packet id |
| risk | `harness.tools.risk_classify` | allow / ask / deny, reason |
| route | `confidence_route` | route, probability |
| budget | `budget_and_stuck_guard` | ok, reason |
| consistency | `residual_consistency` | ok, issue count |
| eat | `eat_filter` | action, reason |
| review | `zeus_head` | applied, reviewers, reason |
| checkpoint | `Hades.save` | checkpoint id, verified, packet hash |
| lesson | `LessonStore` | stored / loaded count |

Fields are whitelisted and capped, so prompts, page text, file content, and
secrets never reach the file. With no open run, `emit` does nothing. Each
chat turn (`run_assist`) and each Add facts save is one run.

Iris side (read-only): `list_runs`, `read_run`, `replay` (plain words).
Admin endpoints: `GET /api/v1/runs`, `GET /api/v1/runs/{id}`, `GET /api/v1/lessons`.
All are admin-only. The UI is under Admin → Diagnostics → Runs and replay.

## Coherence metrics
These metrics guard the leveled harness (`docs/harness/CONSTRAINTS.md`).
They are read-only and use real counts.

- From the trace, `run_trace.coherence()` reports:
  - residual consistency: the share of `consistency` checks that held
  - verification rate: the share of decided runs that ended verified (reviewers approved, a verified checkpoint, or a stored lesson)
  - budget efficiency: the share of budget checks that were within budget
  - abstain rate
- Whether holding back was *correct* needs labels, so that number comes only from the held-out suite.
- The held-out suite is `harness_equal_budget.held_out(params)`: the same 40 Eat candidates plus 24 labelled routing cases. It is never used for tuning. It reports:
  - residual consistency
  - verification rate (right answers out of answered cases)
  - correct abstention (should-not cases held back)
  - budget efficiency (right outcomes per budget unit)

  With the default thresholds the scores are 1.0, 0.846, 0.944 and 1.0. With `route_mid` lowered to 0.6, verification falls to 0.706 and correct abstention to 0.861. `guard_l2` reverts that change.
- Endpoint: `GET /api/v1/coherence` (admin-only); add `?held_out=true` to also run the suite. Shown in Admin → Reports → Coherence.

## Lesson memory
`kin/lesson_store.py`. It writes only after a verified cycle
(`review_proof_verified`: every reviewer approved and verify passed), and
stores only `{lesson, packet_hash, ts}`, one file per owner (individual
tier) under `RESILEOS_LESSONS_DIR`. Relevance uses a VSA bundle
(`LatentHub.encode`), with no outside embeddings. `load_into(packet, query, k)`
puts the k best lessons on a fresh `ControlPacket` as guides
(`guides_loaded` / `guide_bodies`) without replaying history. Loading is optional.

## Equal-budget comparison (measured)
`scripts/harness_equal_budget.py` runs the same 40 outside candidates and the same 40-write budget through two paths:
- direct `Titanos.learn`
- `eat_commit_envelopes`

The 40 candidates are:
- 16 good bounded facts
- 10 prose lines
- 5 `sys:` injections
- 5 overlaps with a stored fact
- 4 duplicates carrying `likes`

| | writes | correct stored | wrong stored | duplicates | wall ms |
|---|---|---|---|---|---|
| without harness | 40 | 16 | 24 | 4 | ~31–33 |
| with harness | 16 | 16 | 0 | 0 | ~25–26 |

Box run, 2026-11-13. Wall time varies by machine; the counts are deterministic.

The first run found that the harness also wrote the 4 in-batch duplicates.
`eat_commit_envelopes` now abstains on a duplicate inside one batch
(`duplicate_in_batch`), and the table above is after that fix.
