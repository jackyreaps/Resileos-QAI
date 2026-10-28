# Resileos-QAI

## What this is

Resileos-QAI is a low-compute knowledge graph engine. It ingests
`(subject, relation, object)` facts, stores them in a compressed
hypervector representation, and answers multi-hop relational queries —
**without calling an external LLM**.

**Why it's cheap to run:** the classical core uses Vector Symbolic
Architecture operations (element-wise binding, bundling, and cleanup)
instead of transformer attention. A $5/month instance handles what would
otherwise require GPU infrastructure.

**What it is not (yet):** a language model, a quantum computer, or a
trillion-token retrieval system. See
[RES-313](docs/310-hierarchy/capacity-law.md) for explicit non-goals.

Hybrid Classical Residual Core + HDRIFT Generative Substrate.

    Classical Residual Core
        -> Control Packet
        -> HDRIFT Generative Substrate
        -> (optional) Quantum / Coherence Backend

QAI names the ambition. The quantum layer is speculative and gated
downstream of a trained and measured classical loop. See
`docs/500-notes/roadmap.md`.

## Documentation

- **Index:** [`docs/readme.md`](docs/readme.md)
- **Changelog:** [`changelog.md`](changelog.md)
- **Version:** [`version`](version)
- **License:** [`LICENSE`](LICENSE)

## Install

    pip install -e ".[all,dev]"

Installs the classical core, the Titanos application layer, the
substrate two-head system, the FastAPI backend, the Streamlit console,
and the test suite in one shot.

Minimal install (core only):

    pip install -e .

## Live console

Two processes. Two terminals.

**Terminal 1 — backend (FastAPI):**

    uvicorn app:app --port 8000 --reload

### Endpoints

Titanos:
- `GET  /api/v1/stats` — store stats
- `GET  /api/v1/ready` — readiness probe (503 until store is open)
- `POST /api/v1/learn` — add one fact
- `POST /api/v1/learn_batch` — add many facts
- `POST /api/v1/query` — single-hop query (routed through Zeus; falls through to parent on decline). Optional `render=true` attaches `answer_text` from the mouth backend.
- `POST /api/v1/sparql` — SPARQL-like queries (RES-322)
- `POST /api/v1/chain` — multi-hop chain
- `POST /api/v1/answer` — retrieve + render (RES-327)
- `GET  /api/v1/answer/backends` — backend availability report
- `POST /api/v1/save` — persist state to disk

Substrate (QD-TER two-head system):
- `GET  /api/v1/substrate_stats` — head stats and training status
- `POST /api/v1/train_substrate` — train the two heads
- `POST /api/v1/verify_manifold` — gated validation (requires is_trained)
- `POST /api/v1/sweep_epsilon` — ε-sweep diagnostic (ungated)

leCore integration (capability router):
- `GET  /api/v1/lecore/health` — leCore bridge liveness
- `POST /api/v1/lecore/route` — capability search via leCore

**Terminal 2 — dashboard (Streamlit):**

    streamlit run ui.py --server.port 8501

Then open `http://localhost:8501`. Five tabs: single-fact ingestion,
batch CSV upload, substrate query with convergence trace, multi-hop
chain, and ε-sweep verification.

The backend keeps the Titanos substrate in memory and persists it to
`titanos_live_state.json` after every write. Restart and it reloads.
Substrate training state persists to `data/substrate_state.pt` (override
with `RESILEOS_SUBSTRATE_STATE`).

## Command-line runs

    # Hybrid validation (HDRIFT)
    python scripts/run_hybrid.py --config configs/example-run.json

    # Hybrid validation + Titanos application block
    python scripts/run_hybrid.py --config configs/titanos-run.json --titanos

    # Titanos demo (in-process, no server)
    python scripts/titanos.py

    # FEP ε-sweep (numerical verification of RES-600 §4)
    python scripts/run_fep_sweep.py --simulate --dim 128 --seq-len 64 \
        --metric rmse --out report_sweep_rmse.json

The sweep returns a fitted slope of `log(residual)` vs `log(ε)`. A slope
near 1 under the `rmse` metric is consistent with the linear `O(ε)`
residual bound in RES-600 §4. See `docs/600-qdter/integration.md` §7.

## Status

- Documentation set: **1.0.0** (RES-000 ... RES-900)
- Classical core and substrate contracts: **stable**
- Titanos application layer: **prototype**
- QD-TER bridge (RES-600 ... RES-603): **conditional / conjectural**
- Quantum / coherence backend: **speculative**

## Layout

    README.md               this file
    changelog.md            version history
    version                 current release string
    LICENSE                 Apache-2.0
    pyproject.toml          build + install metadata
    app.py                  FastAPI backend (Titanos + substrate)
    ui.py                   Streamlit dashboard (5 tabs)
    titanos.py              root shim -> scripts/titanos.py
    scripts/                run_hybrid.py, run_fep_sweep.py, titanos.py
    src/resileos/           frozen classical core + substrate
    src/resileos/substrate/ QD-TER two-head system (RES-600/601/602)
    configs/                run configs and example corpus
    tests/                  acceptance tests
    docs/                   numbered documentation set (RES-000 ... RES-900)
    docs/600-qdter/         QD-TER bridge docs (RES-600 ... RES-603)
