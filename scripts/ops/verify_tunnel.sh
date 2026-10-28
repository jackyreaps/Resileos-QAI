#!/usr/bin/env bash
set -uo pipefail
: "${TUNNEL_TOKEN:?export TUNNEL_TOKEN first}"
: "${RESILEOS_TEST_KEY:?export RESILEOS_TEST_KEY first}"
: "${RESILEOS_HOST:?export RESILEOS_HOST=api.yourdomain.dev}"

# 1. Recreate so the new TUNNEL_TOKEN is picked up
docker compose up -d --force-recreate

# 2. Confirm the tunnel registered
for _ in $(seq 1 30); do
  docker compose logs resileos 2>&1 | grep -qi "Registered tunnel connection" && break
  sleep 2
done
docker compose logs resileos 2>&1 | grep -i "Registered tunnel connection" \
  && echo "PASS  tunnel registered" \
  || { echo "FAIL  tunnel did not register"; docker compose logs resileos | tail -50; exit 1; }

# 3. Still zero published ports
pub=$(docker compose ps --format json | jq -r '[.[] | (.Publishers // []) | length] | add // 0')
[ "$pub" = "0" ] && echo "PASS  0 publishers after recreate" || { echo "FAIL  publishers=$pub"; exit 1; }

# 4. External reachability (run these from ANOTHER machine too)
printf '\nexternal /healthz:  '; curl -s -o /dev/null -w '%{http_code}\n' "https://$RESILEOS_HOST/healthz"
printf 'external /stats (no key): '; curl -s -o /dev/null -w '%{http_code}\n' "https://$RESILEOS_HOST/api/v1/stats"
printf 'external /stats (key):    '; curl -s -o /dev/null -w '%{http_code}\n' \
  -H "X-API-Key: $RESILEOS_TEST_KEY" "https://$RESILEOS_HOST/api/v1/stats"

# 5. Nothing listening on the host
echo "host listeners on 8000/8501 (expect none):"
ss -tlnp 2>/dev/null | grep -E ':(8000|8501)\b' || echo "  (none)"
