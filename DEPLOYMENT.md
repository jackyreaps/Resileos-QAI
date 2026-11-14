# Deployment Checklist

## 1. Prepare configs

```bash
mkdir -p configs
cp configs/api_keys.example.json configs/api_keys.json
python scripts/hash_api_key.py
```

Paste the hash into `configs/api_keys.json` and save the plaintext key somewhere safe.

## 2. Set environment

```bash
export TUNNEL_TOKEN="..."
export RESILEOS_CORS_ORIGINS="https://app.yourdomain.dev"   # optional
export RESILEOS_RATE_LIMIT_PER_MIN=60
```

The API key file is read from `configs/api_keys.json` (mounted read-only). You do not need `RESILEOS_API_KEYS` if the file is present.

## 3. Create the state file and make it writable by the container

```bash
touch titanos_live_state.json
chmod 666 titanos_live_state.json
```

**Why:** the container runs as uid 10001 (`resileos`). A file created by `touch` as root is mode 644 (`rw-r--r--`), so the container cannot write to it and `POST /api/v1/learn_batch` fails with `PermissionError: [Errno 13]`. `chmod 666` makes it world-writable, which is acceptable on a single-user VPS but not on a shared host.

If you prefer not to use `666`, the alternative is:

```bash
sudo chown 10001:10001 titanos_live_state.json
chmod 644 titanos_live_state.json
```

This works on any host where you can `chown` to arbitrary UIDs (i.e., not rootless Docker).

## 4. Build and start

```bash
docker compose build
docker compose up -d
docker ps
```

Expected: the container appears with no `0.0.0.0:*` port mappings. Only the Cloudflare Tunnel connects outbound.

## 5. Verify auth

```bash
# Must be 401
curl -i http://127.0.0.1:8000/api/v1/stats

# Must be 200
curl -i http://127.0.0.1:8000/api/v1/stats \
  -H "X-API-Key: your-plaintext-key"
```

## 6. Verify the tunnel

```bash
curl -i https://api.yourdomain.dev/healthz
curl -i https://api.yourdomain.dev/api/v1/stats \
  -H "X-API-Key: your-plaintext-key"
```

## 7. Train and persist the substrate

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/train_substrate \
  -H "X-API-Key: your-plaintext-key" \
  -H "Content-Type: application/json" \
  -d '{"steps":10}'

docker compose restart
curl -s http://127.0.0.1:8000/api/v1/substrate_stats \
  -H "X-API-Key: your-plaintext-key"
```

`is_trained` and `training_steps` must survive the restart.

## 8. Rollback

```bash
docker compose down
docker compose up -d --force-recreate
```

State survives because it lives in named volumes, not the container.

## 9. Lean proof checks (optional)

Chat checks Lean proofs that people attach (`.lean`) or paste in a
```` ```lean ```` block, through `POST /api/v1/verify/lean`
(`src/resileos/verify/lean_check.py`). Without Lean on the host it answers
`UNAVAILABLE`. It never reports a pass it didn't get. A check never learns
and never changes `require_verified`.

What the host needs:

1. **elan + Lean.** Build the image with
   `docker compose build --build-arg LEAN_TOOLCHAIN=leanprover/lean4:v4.15.0`.
   That installs elan for the `resileos` user (`/home/resileos/.elan/bin`
   on `PATH`). Outside Docker:
   `curl -sSfL https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh | sh -s -- -y --default-toolchain leanprover/lean4:v4.15.0`.
   Run `lean --version` once so the toolchain downloads at build time and
   not on the first check.
2. **Mathlib (optional).** Plain `lean` checks core Lean only. For
   `import Mathlib`, create a Lake project with Mathlib, run `lake exe cache get`,
   and set `RESILEOS_LEAN_PROJECT=/path/to/project` so checks run as
   `lake env lean` inside it.
3. **No network for the checker.** By default each check runs under
   `unshare -rn` (an empty network namespace; util-linux, already in
   Debian images). Test it in the container: `docker compose exec api unshare -rn true`.
   If that fails, Docker's seccomp profile blocks user namespaces. Either
   allow them for this container, or run the API with no egress and set
   `RESILEOS_LEAN_NETWORK=off`. Until one of those is true, checks answer
   `UNAVAILABLE`.

Limits (env, all optional):

| Variable | Default | Meaning |
|---|---|---|
| `RESILEOS_LEAN_BIN` | `lean` on `PATH` | Lean binary |
| `RESILEOS_LEAN_TIMEOUT_S` | 60 (max 300) | Wall-clock limit per check |
| `RESILEOS_LEAN_MEMORY_MB` | 2048 | `lean --memory` limit |
| `RESILEOS_LEAN_MAX_BYTES` | 200000 | Largest source accepted |
| `RESILEOS_LEAN_NETWORK` | `isolate` | `isolate` needs `unshare -rn`; `off` only behind a no-egress host |

The checker also sets CPU, file-size, and core-dump rlimits, runs in a
fresh temp HOME with a scrubbed environment, and refuses source that
runs code (`#eval`, `IO`, `run_cmd`, `extern`, `unsafe`, `initialize`, ...).

## 10. User files

Signed-in people can keep files (`/files`, `GET/POST/DELETE /api/v1/files`).
They are stored per API key under `RESILEOS_FILES_DIR` (default
`data/files`; the image sets `/app/data/files`, so keep `/app/data` on a
volume). They are personal only: nothing is promoted to a hub and
nothing learns from them. Limits: `RESILEOS_FILE_MAX_BYTES` (10 MB),
`RESILEOS_FILES_MAX_TOTAL` (100 MB per account), `RESILEOS_FILES_MAX_COUNT`
(200). Allowed types: png, jpg, webp, gif, mp4, webm, mov, txt, md, csv,
json, py, lean. Images and clips are checked by their file signature.
Files are tied to the account's key, so rotating the key starts an empty
list (see the PR notes).
