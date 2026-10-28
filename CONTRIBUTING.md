# Contributing

## Frozen vs. open surfaces

- `src/resileos/core/` — frozen. Do not modify without a RES-document proposal.
- `src/resileos/substrate/` — stable contracts. Changes require review against RES-300–307.
- `app.py`, `asgi.py`, `ui.py`, `middleware/`, `scripts/`, `Dockerfile` — open for contribution.

## Process

1. Open an issue describing the change and the affected RES document.
2. Submit a PR with tests. `pytest` must pass.
3. Do not add authentication bypasses or public port bindings.

## Local checks

```bash
pip install -e ".[all]"
pytest
python scripts/run_fep_sweep.py --simulate
