#!/usr/bin/env bash
# Container-internal verification. Requires: docker compose, curl, jq.
set -uo pipefail

: "${RESILEOS_TEST_KEY:?export RESILEOS_TEST_KEY='<your key>' first}"
PASS=0; FAIL=0
ok()  { printf 'PASS  %s\n' "$1"; PASS=$((PASS+1)); }
bad() { printf 'FAIL  %s\n' "$1"; FAIL=$((FAIL+1)); }
api() { docker compose exec -T resileos curl -s "$@"; }

# ── pre-flight ────────────────────────────────────────────────────────
touch titanos_live_state.json
[ -f titanos_live_state.json ] \
  && ok "pre-flight: state file is a regular file" \
  || bad "pre-flight: state file is not regular (Docker likely made a dir)"

# ── build + start ─────────────────────────────────────────────────────
docker compose build -q || { bad "build failed"; exit 1; }
docker compose up -d       || { bad "up failed"; exit 1; }

for _ in $(seq 1 60); do
  api -sf http://127.0.0.1:8000/healthz >/dev/null 2>&1 && break
  sleep 2
done

# ── 1/5 healthz ───────────────────────────────────────────────────────
api -sf http://127.0.0.1:8000/healthz | grep -q '"ok":true' \
  && ok "1/5 healthz returns {ok:true}" \
  || bad "1/5 healthz"

# ── 2/5 auth: 401 without key ─────────────────────────────────────────
c=$(api -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/api/v1/stats)
[ "$c" = "401" ] && ok "2/5 /stats without key -> 401" || bad "2/5 /stats without key -> $c"

# ── 3/5 auth: 200 with key ────────────────────────────────────────────
c=$(api -o /dev/null -w '%{http_code}' \
      -H "X-API-Key: $RESILEOS_TEST_KEY" \
      http://127.0.0.1:8000/api/v1/stats)
[ "$c" = "200" ] && ok "3/5 /stats with key -> 200" || bad "3/5 /stats with key -> $c"

# ── 4/5 train: training_steps advances by exactly 10 ──────────────────
# Delta, not absolute — works whether or not a prior volume exists.
before=$(api -H "X-API-Key: $RESILEOS_TEST_KEY" \
           http://127.0.0.1:8000/api/v1/substrate_stats | jq -r .training_steps)
api -X POST -H "X-API-Key: $RESILEOS_TEST_KEY" -H 'Content-Type: application/json' \
    -d '{"steps":10}' http://127.0.0.1:8000/api/v1/train_substrate >/dev/null
after=$(api -H "X-API-Key: $RESILEOS_TEST_KEY" \
          http://127.0.0.1:8000/api/v1/substrate_stats | jq -r .training_steps)
delta=$(( after - before ))
[ "$delta" -eq 10 ] \
  && ok "4/5 train: steps $before -> $after (delta 10)" \
  || bad "4/5 train: delta $delta, expected 10 ($before -> $after)"

# ── 5/5 restart persistence ───────────────────────────────────────────
docker compose restart resileos >/dev/null
for _ in $(seq 1 60); do
  api -sf http://127.0.0.1:8000/healthz >/dev/null 2>&1 && break
  sleep 2
done
s=$(api -H "X-API-Key: $RESILEOS_TEST_KEY" http://127.0.0.1:8000/api/v1/substrate_stats)
trained=$(jq -r .is_trained <<<"$s")
steps=$(jq -r .training_steps <<<"$s")
if [ "$trained" = "true" ] && [ "$steps" = "$after" ]; then
  ok "5/5 persistence: is_trained=$trained steps=$steps survived restart"
else
  bad "5/5 persistence: is_trained=$trained steps=$steps (expected true / $after)"
fi

# ── port exposure ─────────────────────────────────────────────────────
pub=$(docker compose ps --format json | jq -r '[.[] | (.Publishers // []) | length] | add // 0')
[ "$pub" = "0" ] && ok "ports: 0 publishers" || bad "ports: $pub publisher(s)"

mapped=$(docker ps --format '{{.Names}}\t{{.Ports}}' | grep -cE ':[0-9]+->')
[ "$mapped" -eq 0 ] && ok "ports: 0 host mappings" || bad "ports: $mapped host mapping(s)"

printf -- '---\nPASS=%d FAIL=%d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
