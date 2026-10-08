# Resileos-QAI

Hybrid Classical Residual Core + HDRIFT Generative Substrate.

    Classical Residual Core → Control Packet → HDRIFT Generative Substrate
    → (optional) Quantum / Coherence Backend

QAI names the ambition. The quantum layer is speculative and gated downstream
of a trained and measured classical loop. See `docs/500-notes/roadmap.md`.

## Documentation

- **Index:** [`docs/readme.md`](docs/README.md)
- **Changelog:** [`CHANGELOG.md`](CHANGELOG.md)
- **Version:** [`VERSION`](VERSION)
## Install

    pip install -e .

## Quick start

    python -m resileos.validation --config configs/example-run.json --out report.json

## Status

- Documentation set: **1.0.0** (first published).
- Classical core and substrate contracts: **stable**.
- Quantum / coherence backend: **speculative**.

## Layout

    docs/          numbered documentation set (RES-000 … RES-900)
    src/resileos/  reference implementation
    configs/       example run and training configs
    tests/         acceptance tests
