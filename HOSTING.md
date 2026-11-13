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

```bash
git clone https://github.com/jackyreaps/Resileos-QAI.git
cd Resileos-QAI
touch titanos_live_state.json
chmod 666 titanos_live_state.json
mkdir -p configs
cp configs/api_keys.example.json configs/api_keys.json
```

**Why `chmod 666`:** the container runs as uid 10001. A file created by `touch` as root is mode 644, so the container cannot write to it and `POST /api/v1/learn_batch` fails with `PermissionError`. On a shared host, use `chown 10001:10001` + `chmod 644` instead. See `SECURITY.md`.

Generate a key and put its hash into `configs/api_keys.json`:

```bash
python scripts/hash_api_key.py
```

Example result:

```text
key: Kx8...your-plaintext-key...
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

If `asgi.py` is the entry point, `/healthz` is public. If you are running `app.py` directly, `/healthz` does not exist and a 404 does not mean the process is down.

```bash
# With asgi:app (production)
curl -sf http://127.0.0.1:8000/healthz

# Always available
curl -sf http://127.0.0.1:8000/api/v1/ready
curl -sf http://127.0.0.1:8000/api/v1/substrate_stats

# If leCore is configured
curl -sf http://127.0.0.1:8000/api/v1/lecore/health
```

- `GET /healthz` — liveness (public, no auth)
- `GET /api/v1/ready` — readiness; **503** until the Titanos store is open
- `GET /api/v1/substrate_stats` — head state / bridge lock
- `GET /api/v1/lecore/health` — leCore bridge liveness (when configured)

Point container healthchecks at `/healthz` **and** `/api/v1/ready`. The Dockerfile does both.

## 4. Auth, rate limits, CORS

Auth is implemented in `middleware/auth.py` and wired in `asgi.py`.

- Send `X-API-Key: <key>` or `Authorization: Bearer <key>`.
- Monthly quotas are enforced per key and reset on the calendar month (the host clock, same as before). `tier: enterprise` with `quota: 0` is unlimited.
- Per-minute rate limit defaults to 60; override with `RESILEOS_RATE_LIMIT_PER_MIN`.
- Browser CORS origins are set with `RESILEOS_CORS_ORIGINS` (comma-separated). Leave empty for server-to-server only.
- Pages-minted keys are read from Cloudflare KV. File and env keys above still work. A record with `"revoked": true` is rejected.
- Signed-out chat is a per-IP daily trial, not a shared key. The Pages proxy sends `X-Resileos-Trial` plus an HMAC. Default allowance is 20 requests per IP per UTC day.

### Pages key directory (Cloudflare KV)

The API looks up `key:<sha256>` in the `resileos-keys` namespace. It never reads seal or session values. Cache TTL defaults to 30 seconds, so a revocation shows up on the next refresh after that.

Create an API token with **Account → Workers KV Storage → Read**. Set these on the API host (shell or an uncommitted env file, never git):

```bash
export CLOUDFLARE_API_TOKEN='...'          # Workers KV Storage Read
export CLOUDFLARE_ACCOUNT_ID='...'
export CLOUDFLARE_KV_NAMESPACE_ID='463f5f1f1d0a484fb3b9a8e79f0fc413'
export RESILEOS_KV_CACHE_TTL='30'          # optional, seconds
export RESILEOS_PROXY_SECRET='...'         # same value as the Pages secret
export RESILEOS_TRIAL_DAILY_LIMIT='20'     # optional, per IP per UTC day
```

`RESILEOS_PROXY_SECRET` must match the Pages project. Without it, anonymous trial requests are rejected and visitors are asked to sign in.

Rebuild and restart so the container picks up the variables. No host ports are published:

```bash
docker compose build
docker compose up -d
docker compose exec resileos printenv CLOUDFLARE_ACCOUNT_ID
curl -sf http://127.0.0.1:8000/healthz
```

`printenv` should show the account id only. Do not print `CLOUDFLARE_API_TOKEN` or `RESILEOS_PROXY_SECRET`. Existing `API_KEYS_PATH`, `RESILEOS_API_KEYS`, and `RESILEOS_API_KEY` keep working when the token is unset; KV-minted keys then return 403 until the token is set.

Free-tier records minted by Pages use `tier: free` and `quota: 5000` per calendar month. Builder and Founding Builder are `pro` / 100000. Team is `pro` / 500000. Org is `enterprise` / 0.

Bootstrap without a file:

```bash
export RESILEOS_API_KEYS='{"my-key":{"name":"bootstrap","tier":"enterprise","quota":0}}'
```

## 5. Cloudflare Tunnel (zero inbound ports)

```bash
cloudflared tunnel login
cloudflared tunnel create resileos-prod
cloudflared tunnel route dns resileos-prod api.example.com
cloudflared tunnel route dns resileos-prod console.example.com
cloudflared tunnel token resileos-prod
```

Set `TUNNEL_TOKEN` and start the container. The container opens an outbound connection only. `docker ps` must show **no** `0.0.0.0:*` mappings.

## 6. Persistence

| Path | Contents |
|---|---|
| `titanos_live_state.json` | Titanos band store (bind mount) |
| `/app/data/substrate_state.pt` | Substrate heads, optimizer, `is_trained` (named volume) |
| `/app/data/usage.json` | Per-key monthly usage (named volume) |

Back up the bind mount and the named volume. The bind mount must be writable by uid 10001.

## 7. Ops metrics probe

Run it **inside the container** when ports are unpublished:

```bash
docker compose exec -T -e RESILEOS_API_KEY="$RESILEOS_TEST_KEY" \
  resileos python3 scripts/ops/run_ops_metrics.py --phase learn

docker compose restart resileos

docker compose exec -T -e RESILEOS_API_KEY="$RESILEOS_TEST_KEY" \
  resileos python3 scripts/ops/run_ops_metrics.py --phase verify
```

The report is written inside the container at `artifacts/report_ops_metrics.json`. Copy it out:

```bash
docker compose cp resileos:/app/artifacts/report_ops_metrics.json ./report_ops_metrics.json
```

## 8. What this host is not

- **Not a generative LLM.** No next-token head. Answers are structured rows.
- **Not horizontally scalable as-is.** One process, one store.
- **Not a quantum computer.** The substrate is a classical phase field with quantum-shaped mathematics (RES-308).
