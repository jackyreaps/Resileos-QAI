# Resileos-QAI

Resileos-QAI: a layered architecture for residual compression and generative
hypervector dynamics, with a gated quantum backend.

## What this is

Resileos-QAI is a low-compute knowledge graph engine. It ingests
`(subject, relation, object)` facts, stores them in a compressed hypervector
representation, and answers multi-hop relational queries — **without calling an
external LLM**.

**Why it's cheap to run:** the classical core uses Vector Symbolic Architecture
operations (element-wise binding, bundling, and cleanup) instead of transformer
attention. A $5/month instance handles what would otherwise require GPU
infrastructure.

**What it is not:** a language model, a quantum computer, or a trillion-token
retrieval system. See [RES-313](docs/310-hierarchy/capacity-law.md) for explicit
non-goals.

```
Classical Residual Core -> Control Packet -> HDRIFT Generative Substrate
    -> (optional) Quantum / Coherence Backend
```

QAI names the ambition. The quantum layer is speculative and gated downstream of
a trained and measured classical loop. See `docs/500-notes/roadmap.md`.

## Status

| Layer | Status |
|---|---|
| Classical Core (RES-200–202) | **Frozen / stable** |
| Substrate (RES-300–307) | **Stable contracts** |
| Titanos Application Layer | **Prototype** |
| QD-TER Bridge (RES-600–603) | **Conditional / conjectural** |
| Quantum Backend | **Speculative** |

### Product surface status

| Surface | Route | On the hosted API? |
|---|---|---|
| Learn / batch / query / chain / SPARQL / answer | `/api/v1/*` | **Yes** |
| Tool schemas for external mouths | `GET /api/v1/tools` | **Yes** |
| Substrate stats / train / verify / sweep | `/api/v1/substrate_*`, `/api/v1/sweep_epsilon` | **Yes** |
| leCore router | `/api/v1/lecore/*` | **Yes** |
| World asset registry | `/api/v1/world/*` | **No — in `src/resileos`, not mounted** |
| Guild workspace | `/api/v1/guild/*` | **No — in `src/resileos` + `scripts/guild_console.py`, not mounted** |

Do not sell seats or asset storage until the corresponding routes are mounted
and smoke-tested on the deployed host. See
[docs/marketing/pricing.md](docs/marketing/pricing.md).

## Documentation

- **Index:** [`docs/readme.md`](docs/readme.md)
- **Changelog:** [`changelog.md`](changelog.md)
- **Version:** [`version`](version)
- **License:** [`LICENSE`](LICENSE)
- **Hosting:** [HOSTING.md](HOSTING.md)
- **Deployment checklist:** [DEPLOYMENT.md](DEPLOYMENT.md)
- **Security:** [SECURITY.md](SECURITY.md)
- **Contributing:** [CONTRIBUTING.md](CONTRIBUTING.md)
- **Pricing and packaging:** [docs/marketing/pricing.md](docs/marketing/pricing.md)
- **Customer onboarding:** [docs/customer/onboarding.md](docs/customer/onboarding.md)

## Install

```bash
pip install -e ".[all,dev]"
```

Installs the classical core, the Titanos application layer, the substrate
two-head system, the FastAPI backend, the Streamlit console, and the test
suite in one shot.

Minimal install (core only):

```bash
pip install -e .
```

## Quick start

### Docker (recommended)

```bash
git clone https://github.com/jackyreaps/Resileos-QAI.git
cd Resileos-QAI
touch titanos_live_state.json
chmod 666 titanos_live_state.json
mkdir -p configs
cp configs/api_keys.example.json configs/api_keys.json
python scripts/hash_api_key.py
# Paste the hash into configs/api_keys.json
docker compose up -d --build
```

No host ports are published. Access the API and console via an SSH tunnel or a
Cloudflare Tunnel. See [HOSTING.md](HOSTING.md).

### Local development

Two processes, two terminals.

**Terminal 1 — backend (FastAPI):**

```bash
uvicorn asgi:app --port 8000 --reload
```

`asgi:app` is the only entrypoint that installs `middleware/auth.py`. Running
`app:app` directly fails closed (503) unless `RESILEOS_AUTH_BYPASS=1` is set.
Do not use the bypass outside local development.

**Terminal 2 — dashboard (Streamlit):**

```bash
streamlit run ui.py --server.port 8501
```

Then open `http://localhost:8501`. Five tabs: single-fact ingestion, batch CSV
upload, substrate query with convergence trace, multi-hop chain, and ε-sweep
verification.

The backend keeps the Titanos substrate in memory and persists it to
`titanos_live_state.json` after every write. Restart and it reloads.

### Endpoints

Titanos:

- `GET  /api/v1/stats` — store stats
- `GET  /api/v1/ready` — readiness probe (503 until store is open)
- `POST /api/v1/learn` — add one fact
- `POST /api/v1/learn_batch` — add many facts
- `POST /api/v1/query` — single-hop query (routed through Zeus; falls through
  to parent on decline). Optional `render=true` attaches `answer_text` from the
  mouth backend.
- `POST /api/v1/sparql` — SPARQL-like queries (RES-322)
- `POST /api/v1/chain` — multi-hop chain
- `POST /api/v1/answer` — retrieve + render (RES-327); unresolved free-text →
  `NONE_CHANNEL`
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

## Configuration

| Environment variable | Purpose |
|---|---|
| `RESILEOS_API_KEYS` | JSON map of `{plaintext-key: {name, tier, quota}}` |
| `RESILEOS_API_KEY` | Legacy single-key (hashed on load) |
| `API_KEYS_PATH` | Path to the hashed key file (default `configs/api_keys.json`) |
| `RESILEOS_AUTH_BYPASS` | `1` disables auth. Local dev only. |
| `RESILEOS_RATE_LIMIT_PER_MIN` | Per-minute rate limit (default 60) |
| `RESILEOS_CORS_ORIGINS` | Comma-separated browser origins |
| `RESILEOS_SUBSTRATE_STATE` | Substrate checkpoint path |
| `TUNNEL_TOKEN` | Cloudflare Tunnel token |
| `RESILEOS_ANSWER_BACKEND` | `auto` \| `structured` \| `local_hf` \| `hosted` |

## Command-line runs

```bash
# Hybrid validation (HDRIFT)
python scripts/run_hybrid.py --config configs/example-run.json

# Hybrid validation + Titanos application block
python scripts/run_hybrid.py --config configs/titanos-run.json --titanos

# Titanos demo (in-process, no server)
python scripts/titanos.py

# FEP ε-sweep (numerical verification of RES-600 §4)
python scripts/run_fep_sweep.py --simulate --dim 128 --seq-len 64 \
    --metric rmse --out report_sweep_rmse.json
```

The sweep returns a fitted slope of `log(residual)` vs `log(ε)`. A slope near 1
under the `rmse` metric is consistent with the linear `O(ε)` residual bound in
RES-600 §4. See `docs/600-qdter/integration.md` §7.

## Testing

```bash
pytest -q
python scripts/run_fep_sweep.py --simulate
bash scripts/ops/verify_container.sh   # requires a Docker host
```

## Layout

```
README.md                       this file
changelog.md                    version history
version                         current release string
LICENSE                         Apache-2.0
pyproject.toml                  build + install metadata
app.py                          FastAPI backend (Titanos + substrate)
asgi.py                         ASGI entrypoint (installs auth middleware)
ui.py                           Streamlit dashboard (5 tabs)
titanos.py                      root shim -> scripts/titanos.py
scripts/                        run_hybrid.py, run_fep_sweep.py, titanos.py
scripts/ops/                    verify_container.sh, verify_tunnel.sh, run_ops_metrics.py
middleware/                     auth.py (API key + quota + rate limit)
configs/                        run configs and example corpus
configs/api_keys.example.json   template for hashed API keys
src/resileos/                   frozen classical core + substrate
src/resileos/substrate/         QD-TER two-head system (RES-600/601/602)
tests/                          acceptance tests
docs/                           numbered documentation set (RES-000 ... RES-900)
docs/600-qdter/                 QD-TER bridge docs (RES-600 ... RES-603)
docs/marketing/                 pricing and packaging
docs/customer/                  onboarding for new customers
landing/                        static landing page (GitHub Pages)
```

## License

Apache-2.0. See [LICENSE](LICENSE).
