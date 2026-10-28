# Operational verification scripts

Not part of the Python import path. Run from the repo root.

## verify_container.sh
Proves the app works inside the container: health, auth (401/200),
training delta of 10 steps, persistence across restart, zero
published ports. Requires: `docker compose`, `jq`.

    export RESILEOS_TEST_KEY='...'
    export RESILEOS_API_KEYS="{\"$RESILEOS_TEST_KEY\":{\"name\":\"bootstrap\",\"tier\":\"enterprise\",\"quota\":0}}"
    ./scripts/ops/verify_container.sh

Exit 0 = all checks passed.

## verify_tunnel.sh
Proves external traffic reaches the service through Cloudflare
Tunnel with zero published ports. Run only after verify_container.sh
is green, and only after `cloudflared tunnel create` has been run.
Requires: `docker compose`, `curl`, `jq`.

    export TUNNEL_TOKEN='...'
    export RESILEOS_TEST_KEY='...'
    export RESILEOS_HOST='api.yourdomain.dev'
    ./scripts/ops/verify_tunnel.sh
