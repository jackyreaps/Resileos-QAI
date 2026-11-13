# Changelog

All notable changes to Resileos-QAI. Semantic Versioning. Doc IDs (`RES-XXX`)
are stable and never reused.

## [Unreleased]

### Added
- `src/resileos/ui/cascade_address.py` — Human Belt, pins, and
  orientation scales on frames (3, 5, 9, 12). Belt means only the
  5-mod Human Belt. `pin_address("local")` is belt 5, frame 5.
  `orientation_scale("orion")` is scale_level 2, frame 9 (no belt
  field). The former orientation name `local` is `edge`. `proportion`
  is the shared core `PHI`; `phi_weight` is φ^{-scale_level}.
  See `docs/200-core/cascade-address.md`.
- `src/resileos/persona/promote.py` — one-step outward subject
  for a verified, opted-in fact. Never re-verifies, never writes.
  Draft mapping local=world / global=org was reversed to match
  hub_train and the persona tiers: individual→user, local→org,
  global→world. See `docs/320-titanos/tier-promotion.md`.
- Optional `pin` and `address` fields on `ControlPacket`/`VideoPacket`
  (default `None`, recorded only; verify gates unchanged).
- `address_for_hub_subject` records the five-pin address for a hub namespace (user→individual, org→local, world→global).
- `encode_sequence` records `kept` from the 1/64 keep floor; TEMPORAL_SIGMA and ACCEPT_ENERGY are unchanged.
- `docs/320-titanos/outer-layer.md` — outer-layer flow: Hermes envelopes → Eat → Zeus
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
- Loose docs at the `docs/` root moved into the existing folders:
  `oscillator-depth.md` → `300-substrate/`, `outer-layer.md` and
  `guild-merit.md` → `320-titanos/`. Cascade address docs now live at
  `docs/200-core/cascade-address.md`; promotion at
  `docs/320-titanos/tier-promotion.md`.
- `docs/readme.md` — RES-600/601/602 added to reading order; 600-series added
  to the categories table. Index also lists cascade address and
  cascade promotion.
- `configs/harness_policy.yaml` — guide path
  `docs/RES-100/architecture.md` updated to
  `docs/100-foundations/architecture.md`.

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
