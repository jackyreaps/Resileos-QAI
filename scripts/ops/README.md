# Operational verification scripts

Not part of the Python import path. Run from the repo root.

## verify_container.sh

Proves the app works inside the container: health, auth (401/200), training delta of 10 steps, **bind-mount write** (learn_batch), persistence across restart, zero published ports.

Requires: `docker compose`, `jq`.

```bash
export RESILEOS_TEST_KEY='...'
export RESILEOS_API_KEYS="{\"$RESILEOS_TEST_KEY\":{\"name\":\"bootstrap\",\"tier\":\"enterprise\",\"quota\":0}}"
bash scripts/ops/verify_container.sh
```

Exit 0 = all checks passed. The script runs `chmod 666 titanos_live_state.json` in pre-flight so the container can write to the bind mount. If you manage that file manually, skip the script and run the checks individually.

## verify_tunnel.sh

Proves external traffic reaches the service through Cloudflare Tunnel with zero published ports. Run only after `verify_container.sh` is green, and only after `cloudflared tunnel create` has been run.

Requires: `docker compose`, `curl`, `jq`.

```bash
export TUNNEL_TOKEN='...'
export RESILEOS_TEST_KEY='...'
export RESILEOS_HOST='api.yourdomain.dev'
bash scripts/ops/verify_tunnel.sh
```

## Note on zero-port deploys

With no published ports, `run_ops_metrics.py` cannot reach the API from the host. Run it inside the container:

```bash
docker compose exec -T -e RESILEOS_API_KEY="$RESILEOS_TEST_KEY" \
  resileos python3 scripts/ops/run_ops_metrics.py --phase learn

docker compose restart resileos

docker compose exec -T -e RESILEOS_API_KEY="$RESILEOS_TEST_KEY" \
  resileos python3 scripts/ops/run_ops_metrics.py --phase verify
```

This is intentional: the auth perimeter is unreachable from outside the container by design. The host cannot reach `127.0.0.1:8000` because nothing is published to it.
