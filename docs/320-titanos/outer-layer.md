# Outer layer: Hermes envelopes, Eat, Zeus reviewers, Titanos

This page describes how outside material reaches Titanos, what Iris and
Hades record about it, and the extra check metrics on a studio clip. It
is the reviewed version of the outer-layer drafts. Every name below is a
module or function on `main` after this change.

## Flow

```
Hermes legion (search_envelope / crawl_envelope)
   │  untrusted candidate envelope: source URL, title, snippet or page text,
   │  retrieved_at, claim = None
   ▼
Eat  kin/eat_envelope.check_envelope
   │  1. strip attention metrics (likes, views, rank, score, buzz, ...)
   │  2. claim must be a structured triple; prose abstains (never parsed)
   │  3. valid_from / valid_to: ISO parse, half-open [from, to) needs from < to;
   │     a bad bound abstains
   │  4. kin/eat.eat_filter (verifier swarm)
   ▼
Eat  kin/eat_envelope.eat_commit_envelopes
   │  5. CONFLICT: a bounded window that overlaps a stored, bounded fact with a
   │     different object (same subject + relation), or another claim in the
   │     same batch, is CONFLICT. Neither side is written. Order does not matter.
   ▼
Zeus harness/separated.zeus_head with harness/separated.default_reviewers
   │  6. verifier swarm (sees the same interval), council when an ask_fn is
   │     given, Athena when asked. Any rejection holds the whole batch.
   ▼
Titanos  Titanos.learn(s, r, o, valid_from=..., valid_to=...)
   │
   ├─ Hades kin/hades_notes.HadesNotes: one summary line (counts only)
   └─ Iris  kin/iris_trace.observe_trace: read-only view of the residual trace
```

Hermes never learns and never writes residual state (`writes_residual`
is false on the Hermes Kin, and the legion gate refuses `learn_fn`
outside Eat). Search and crawl are escalate-only: the legion gate lets
them run only when `confidence_route` says escalate. A Hermes envelope
has no claim, so on its own it abstains at Eat. Turning a snippet into a
triple is not done here; a structured claim has to come from somewhere
that can name its subject, relation, and object.

Eat stays the only writer. Studio, visual, and persona paths do not call
this module, `learn`, the scar matrix, or Titanos.

## What exists and what was added

| Draft item | On `main` before | This change |
| --- | --- | --- |
| Zeus gate, write / review / apply | `harness/separated.py` (`SeparatedCycle`, `zeus_head`, `run_separated`) | Extended: `default_reviewers()` is the one reviewer list; `review_verifiers` reads `temporal_bounds` from proposal metadata |
| Kin and legions | `kin/legions.py` (role table, `register_legion`, gate) | Reused. New legions register through it, off by default |
| Untrusted ingestion via Eat | `kin/eat.py` `eat_filter`, `kin/verifiers.py` (temporal checker) | Added `kin/eat_envelope.py` in front of `eat_filter` |
| Temporal envelope, half-open intervals | Titanos `learn(valid_from, valid_to)`, `_fact_valid_at`, `_explicit_temporal_conflict` (query time) | Write-time overlap check that uses Titanos's own `_parse_temporal` and `_fact_fields` |
| Titanos commit hook | none | `eat_commit_envelopes`: commits only after Eat accepts and every assigned reviewer approves |
| Hermes search / crawl | `harness/legions/search.py` (`web_search`, `scrape_url`) used by the agent loop | `kin/outer_legions.py` wraps them as envelope producers; backends injectable |
| Hermes sandbox | none (no code sandbox in the repo) | `hermes.sandbox_request`: separate opt-in; refused unless `risk_class == "allow"` and a verified Zeus result is supplied; then `UNAVAILABLE`. Never executes |
| Iris trace JSONL | `kin/residual_trace.py` writes `iris.jsonl`; example `iris.jsonl_trace` | `kin/iris_trace.py` read-only sensor and summary; `iris.trace_sensor` legion |
| Hades notes | `kin/hades.py` checkpoints; example `hades.lesson_notes` (free text) | `kin/hades_notes.py` append-only sidecar with a fixed note shape; `hades.lesson_note` legion |
| Kuramoto R, Betti b0 / b1 on video | `studio/clip_codec.py`, `studio/sequence_stage.py`, `VideoPacket` | `studio/clip_metrics.py`; recorded on `VideoPacket.check_metrics` and `check_metrics` in the stage body. Not gating |

## Renames

| Draft name | Name in the repo | Why |
| --- | --- | --- |
| `titanos_store.commit_temporal`, `titano_commit` | `eat_envelope.eat_commit_envelopes` | Eat owns every Titanos write; the real store API is `Titanos.learn(..., valid_from, valid_to)` |
| Eat temporal validator / custom `eat_filter` signature | `eat_envelope.check_envelope` calling the existing `eat_filter(claim)` | Keep one Eat filter |
| "Demi-gods" as Zeus reviewers | `separated.default_reviewers` (verifiers, council, Athena) | In this repo Demi-gods (Themis, Momus, Hephaestus, Atlas, Nike, Morpheus) are separate helpers. The Zeus reviewers are the separated-cycle reviewers |
| Hermes search / crawl | `hermes.search_envelope`, `hermes.crawl_envelope` | Hermes is the messenger across the boundary. It carries what it found and nothing more |
| Hermes sandbox | `hermes.sandbox_request` | It is a request gate, not an executor. If a runtime is added later, running code belongs under Hephaestus's limits |
| Iris `trace_jsonl` | `iris.trace_sensor` (`kin/iris_trace.py`) | Iris observes; the sensor only reads |
| Hades notes | `hades.lesson_note` (`kin/hades_notes.py`) | Hades keeps what crosses attempts: the lesson |
| `ManifoldPhasePacket`, `GraphGeometryVerifier`, `TopologicalInvariantGuard` | `studio/clip_metrics.clip_check_metrics`, `VideoPacket.check_metrics` | No second packet type; the metrics ride on the existing `VideoPacket` |
| "Persistent homology" | per-transition Betti counts | What is computed is b0 / b1 of one thresholded residual, not a persistence diagram |

## Video check metrics

`clip_check_metrics(frames)` runs on the frames the clip decodes to:

- **motion_phase_coherence**: each transition's integer shift (dy, dx)
  from phase correlation; R = |mean exp(iθ)| over the angles of the
  transitions that moved. R is None with fewer than two moving
  transitions. This is the Kuramoto order parameter of those angles; no
  oscillator is simulated and no frame is generated from it.
- **betti**: per transition, the residual F_t − F_{t−1} thresholded at
  `max(1e-3, 0.25 · max|R|)`. b0 = 4-connected active components, b1 =
  8-connected inactive regions not touching the border (holes).
- **betti_stable**: whether every moving transition has the same (b0, b1).

`gating` is false. The verify gate in `sequence_stage._judge` is
unchanged. These numbers are recorded so they can be compared with the
gate's outcome over real clips before anyone proposes using them as a
gate.

Measured on one x86_64 box (Python 3.12, numpy 1.26):

| Call | Time |
| --- | --- |
| `clip_check_metrics`, 8 frames of 16×16, random (mean of 200) | 2.4 ms |
| `clip_check_metrics`, 8 frames of 16×16, moving square (mean of 200) | 3.0 ms |
| `eat_commit_envelopes`, 10 bounded envelopes into a fresh Titanos, including `learn` (mean of 50; construction excluded) | 11.8 ms |

These are milliseconds, not microseconds.

## Left out, and why

- **Stable Video Diffusion (local), Blender MCP, Higgsfield, Seedance,
  Topaz.** Not integrated. Video stays `UNAVAILABLE` with `url` null when
  no provider is configured.
- **Groq, Gemini, OpenRouter, Ollama inference legions.** Excluded under
  the no-outside-LLM-fallback policy. (The existing `ollama_local`
  example on `main` is unchanged: off by default, needs an injected
  function, makes no network call.)
- **Kuramoto trajectory solver as a draft generator.** Advancing phases
  does not produce frames, and nothing has been benchmarked against the
  residual codec. Only the order parameter is used, as a metric.
- **Manifold energy check.** The clip gate already has residual energy
  (`ACCEPT_ENERGY`); a second energy without a definition tied to the
  codec would be a made-up number.
- **SSE telemetry route.** The clip stage runs synchronously and keeps no
  per-job progress, so a stream would have to invent values. Skipped
  until there is real job state to stream.
- **Escalation from a failed metric to an external leaf.** No external
  leaf is configured, and the metrics are not a gate.
- **networkx.** Not needed; the component counts are a few lines of numpy.


## Five-pin address

The 5-pin is a construction on the ordered cascade (3, 5, 9, 12), not
a label. It sits at the 5-frame. See [five-pin](../200-core/five-pin.md) for
the belt, the three pins, the waist (N=36), and the debt quantum
(ε = 1/64). `VideoPacket` and `ControlPacket` record optional `pin`
and `address` fields that default to `None`. They are not a verify
gate.

Visual matrix control on the same cascade of frames is in
[belt-scale](../studio/belt-scale.md). One-step, opt-in promotion of a
verified fact (user → org → world) is in
[cascade promotion](cascade-learn.md).

## Defaults

Nothing here changes `require_verified`, the Metis `allow_mouth`
default, or the verified-cycle mouth policy. All new legions are
registered only by `register_outer_legions(enable=True)`, and the
sandbox gate also needs `enable_sandbox=True`.
