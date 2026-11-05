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

## Architecture stack

```
Classical Residual Core → Control Packet → HDRIFT Generative Substrate → (optional) Quantum / Coherence Backend
```

The quantum layer is speculative and gated downstream of a trained classical
loop. It makes no speedup or coherence claims until experimental
characterization.

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
and smoke-tested on the deployed host. See `docs/marketing/pricing.md`.

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

```bash
pip install -e ".[all]"
uvicorn asgi:app --port 8000 --reload
```

`asgi:app` is the only entrypoint that installs `middleware/auth.py`. Running
`app:app` directly fails closed (503) unless `RESILEOS_AUTH_BYPASS=1` is set.
Do not use the bypass outside local development.

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

## Testing

```bash
pytest -q
python scripts/run_fep_sweep.py --simulate
bash scripts/ops/verify_container.sh   # requires a Docker host
```

## Documentation

- [HOSTING.md](HOSTING.md) — deployment and operations
- [DEPLOYMENT.md](DEPLOYMENT.md) — step-by-step deployment checklist
- [SECURITY.md](SECURITY.md) — security policy and deployment invariants
- [CONTRIBUTING.md](CONTRIBUTING.md) — contribution rules
- [docs/marketing/pricing.md](docs/marketing/pricing.md) — pricing and packaging
- [docs/customer/onboarding.md](docs/customer/onboarding.md) — what to send a
  new customer

## License

Apache-2.0. See [LICENSE](LICENSE).
