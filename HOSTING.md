---
doc: RES-800
title: Hosting Guide
status: stable
depends_on: [RES-320, RES-321, RES-322]
referenced_by: []
---

# Hosting Guide

Deploy Resileos-QAI as a knowledge/query service: Titanos + residual substrate + FastAPI + Streamlit. It is not a next-token generative LLM. Answers come from the band store via `query` / `chain` / SPARQL.

## 1. What runs

| Component | Port | Entry point |
|---|---|---|
| FastAPI backend | 8000 (loopback) | `asgi:app` |
| Streamlit dashboard | 8501 (loopback) | `ui.py` |
| Titanos band store | in-process | `scripts/titanos.py` |
| Residual substrate | in-process | `resileos.substrate` |

Single process. The Titanos store is a module-level singleton. Keep `--workers 1` and one replica unless the store is externalized.

## 2. Quick start (Docker)

Clone and prepare the state file:

```bash
git clone https://github.com/jackyreaps/Resileos-QAI.git
cd Resileos-QAI
touch titanos_live_state.json
mkdir -p configs
cp configs/api_keys.example.json configs/api_keys.json
```

Generate a key and put its hash into `configs/api_keys.json`:

```bash
python scripts/hash_api_key.py
```

Example result:

```text
key:  Kx8...your-plaintext-key...
hash: 3f9a...64-hex-chars...
```

Edit `configs/api_keys.json`:

```json
{
  "3f9a...64-hex-chars...": {"name": "bootstrap", "tier": "enterprise", "quota": 0}
}
```

Build and run:

```bash
docker compose build
docker compose up -d
```

No host ports are published. For local access, use an SSH tunnel:

```bash
ssh -L 8501:127.0.0.1:8501 user@host
```

## 3. Probes

There is **no** `/healthz` route. A 404 on `/healthz` does not mean the
process is down.

```bash
curl -sf http://127.0.0.1:8000/api/v1/ready
curl -sf http://127.0.0.1:8000/api/v1/substrate_stats
# optional, if leCore is configured:
curl -sf http://127.0.0.1:8000/api/v1/lecore/health
```

- `GET /api/v1/ready` — readiness; **503** until the Titanos store is open
- `GET /api/v1/substrate_stats` — head state / bridge lock
- `GET /api/v1/lecore/health` — leCore bridge liveness (when configured)

Point container healthchecks at `/api/v1/ready`, not `/healthz`.

## 4. Auth, rate limits, CORS

Auth is implemented in `middleware/auth.py` and wired in `asgi.py`.

- Send `X-API-Key: <key>` or `Authorization: Bearer <key>`.
- Monthly quotas are enforced per key.
- Per-minute rate limit defaults to 60; override with `RESILEOS_RATE_LIMIT_PER_MIN`.
- Browser CORS origins are set with `RESILEOS_CORS_ORIGINS` (comma-separated). Leave empty for server-to-server only.

Bootstrap without a file:

```bash
export RESILEOS_API_KEYS='{"my-key":{"name":"bootstrap","tier":"enterprise","quota":0}}'
```

## 5. Cloudflare Tunnel (zero inbound ports)

```bash
cloudflared tunnel login
cloudflared tunnel create resileos-prod
cloudflared. tunnel route dns resileos-prod api Pers.example.com
cloudflared tunnel route dnsistence resileos-prod console.example.com
cloudflared tunnel token

 resileos-prod
```

Set `T|UNNEL_TOKEN` and start the container. The container opens an outbound connection only. `docker ps` must show no `0.0.0.0:*` mappings.

##  Path | Contents |
|---|---|
| `titanos_live_state.json` | Titanos band store |
| `/app/data/substrate_state.pt` | Substrate heads, optimizer, `is_trained` |
| `/app/data/usage.json` | Per-key monthly usage |

Both `/app/data` and the state file are mounted as volumes in `docker-compose.yml`. Back them up.

## 7. Smoke queries

```bash
KEY="your-plaintext-key"

curl -s -X POST http://127.0.0.1:8000/api/v1/sparql \
  -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"query":"SELECT ?o WHERE alice --knows--> ?o"}'
```

## 8. What this host is not

- **Not a generative LLM.** No next-token head. Answers are structured rows.
- **Not horizontally scalable as-is.** One process, one store.
- **Not a quantum computer.** The substrate is a classical phase field with quantum-shaped mathematics (RES-308).
