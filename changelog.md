# Changelog

All notable changes to Resileos-QAI. Semantic Versioning. Doc IDs (`RES-XXX`)
are stable and never reused.

## [Unreleased]

### Added
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
- The `Γ = Π_s·G` (source) vs `Γ = G` (derivation) discrepancy is recorded as
  an open item in RES-600 §4.1 and referenced from RES-602 §2. The code in
  `reduction.py` uses the `Γ = G` resolution.

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
