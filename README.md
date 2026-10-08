# Resileos-QAI

Hybrid Classical Residual Core + HDRIFT Generative Substrate.

    Classical Residual Core -> Control Packet -> HDRIFT Generative Substrate
    -> (optional) Quantum / Coherence Backend

QAI names the ambition. The quantum layer is speculative and gated downstream
of a trained and measured classical loop. See `docs/500-notes/roadmap.md`.

## Documentation

- **Index:** [`docs/readme.md`](docs/readme.md)
- **Changelog:** [`changelog.md`](changelog.md)
- **Version:** [`version`](version)
- **License:** [`LICENSE`](LICENSE)

## Install

    pip install -e ".[all]"

Installs the classical core, the Titanos application layer, the FastAPI
backend, the Streamlit console, and the test suite in one shot.

Minimal install (core only):

    pip install -e .

## Live console

Two processes. Two terminals.

**Terminal 1 - backend (FastAPI):**

    uvicorn app:app --port 8000 --reload

Endpoints: `/api/v1/learn`, `/api/v1/learn_batch`, `/api/v1/query`,
`/api/v1/chain`, `/api/v1/stats`, `/api/v1/save`.

**Terminal 2 - dashboard (Streamlit):**

    streamlit run ui.py --server.port 8501

Then open `http://localhost:8501`. Four tabs: single-fact ingestion, batch
CSV upload, substrate query with convergence trace, multi-hop chain.

The backend keeps the Titanos substrate in memory and persists it to
`titanos_live_state.json` after every write. Restart and it reloads.

## Command-line runs

    # Hybrid validation
    python scripts/run_hybrid.py --config configs/example-run.json

    # Hybrid validation + Titanos application block
    python scripts/run_hybrid.py --config configs/titanos-run.json --titanos

    # Titanos demo (in-process, no server)
    python scripts/titanos.py

## Status

- Documentation set: **1.0.0** (RES-000 ... RES-900)
- Classical core and substrate contracts: **stable**
- Titanos application layer: **prototype**
- Quantum / coherence backend: **speculative**

## Layout

    README.md           this file
    changelog.md        version history
    version             current release string
    license             Apache-2.0
    pyproject.toml      build + install metadata

    app.py              FastAPI backend for the live console
    ui.py               Streamlit dashboard
    scripts/            run_hybrid.py, titanos.py
    src/resileos/       frozen classical core + substrate
    configs/            run configs and example corpus
    tests/              acceptance tests
    docs/               numbered documentation set (RES-000 ... RES-900)
