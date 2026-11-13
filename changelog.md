# Changelog

All notable changes to Resileos-QAI. Semantic Versioning. Doc IDs (`RES-XXX`)
are stable and never reused.

## [Unreleased]

### Added
- `src/resileos/ui/belt_scale.py` — visual matrix control. Same
  pentagram at every scale, phi as the proportion. `matrix_control`
  belt is the scale index (orion → belt 2, frame 9), not the 5-mod
  Human Belt. `embed_frame(..., scale=...)` sets the cascade address;
  `suite_residual` still gets the original belt so `residual_bin` is
  unchanged. No image is built. See `docs/studio/belt-scale.md`.
- `src/resileos/answer/cascade_learn.py` — one-step outward subject
  for a verified, opted-in fact. Never re-verifies, never writes.
  Draft mapping local=world / global=org was reversed to match
  hub_train and the persona tiers: individual→user, local→org,
  global→world. See `docs/320-titanos/cascade-learn.md`.
- `src/resileos/ui/five_pin.py` — 5-pin construction on the cascade
  (frames 3, 5, 9, 12) using `cascade_address`. Pins: individual
  (frame 5, edge), local (frame 5, hub), global (frame 9, latent_hub).
  Waist N=36 caps factors (clip, with `within_waist` to refuse).
  Debt quantum ε=1/64: `keep_packet` is false below 1/64, true at
  equality. Persona-store tiers map Individual→individual, Hub→local,
  Latent→global with no promotion. See `docs/five-pin.md`.
- Optional `pin` and `address` fields on `ControlPacket`/`VideoPacket`
  (default `None`, recorded only; verify gates unchanged).
- `docs/outer-layer.md` — outer-layer flow: Hermes envelopes → Eat → Zeus
  reviewers → Titanos; Iris trace sensor; Hades lesson notes; clip check
  metrics. Lists renames from the drafts and what was left out.
- `src/resileos/kin/eat_envelope.py` — temporal envelope check, attention
  metric stripping, write-time interval CONFLICT, commit through `zeus_head`.
- `src/resileos/kin/outer_legions.py` — Hermes `search_envelope`,
  `crawl_envelope`, `sandbox_request` (gate only); Iris `trace_sensor`;
  Hades `lesson_note`. Off by default.
- `src/resileos/kin/iris_trace.py`, `src/resileos/kin/hades_notes.py`.
- `src/resileos/studio/clip_metrics.py` — motion phase coherence (R) and
  residual Betti counts, recorded on `VideoPacket.check_metrics`; not gating.
- `docs/600-qdter/fep-reduction.md` — RES-600, FEP Reduction Bridge
  (`conditional`). Records the QD-TER local reduction, the Γ definition
  discrepancy (§4.1), and the numerical verification harness (§4.2).
- `docs/600-qdter/non-dual-adaptation.md` — RES-601, Non-Dual Adaptation Layer
  (`conjectural`). Records Axioms M/V/Ω, the parallel transport condition, and
  the metric bridge marked "to be supplied" (§7).
- `docs/600-qdter/integration.md` — RES-602, Two-Head Integration Note
  (`draft`). Records the three corrections relative to earlier drafts and the
  orthogonality of the two heads.
- `docs/600-qdter/speculative-cross-stream.md` — RES-603, Speculative
  Cross-Stream Layer (`draft`). Records the DFlash block-diffusion / EAGLE-3
  feature-fusion / tree-attention runtime integration.
- `src/resileos/substrate/geometry.py` — `LowRankMetricHead` (structural proxy
  substitute) and `BridgeMetricHead` (canonical metric bridge, locked).
- `src/resileos/substrate/reduction.py` — `VerifiableFEPReductionHead`,
  `sweep_epsilon`, `simulate_linear_ode`.
- `src/resileos/substrate/__init__.py` — substrate package.

### Changed
- `docs/readme.md` — RES-600/601/602 added to reading order; 600-series added
  to the categories table.

### Notes
### Notes
- The Γ = Π_s·G (source) vs Γ = G (derivation) discrepancy is resolved as a transcription error in the source. RES-600 §4.1 now records the resolution; RES-602 §2 reflects it. The code in reduction.py implements Γ = G.

## [1.0.0] — 2026-10-08

### Added
- Initial published documentation set (RES-000 – RES-900).
- Foundations: overview, architecture, design principles.
- Classical core: residual invariants, control packet, canonicalization.
- Substrate: HDRIFT adapter, moment bundle, abstention, sigma gate.
- Operations: run config, training, validation.
- Notes: behavioral semantics, roadmap.
- Reference: glossary, JSON schemas.
- Reference implementations under `src/resileos/`.
- Acceptance tests under `tests/`.
