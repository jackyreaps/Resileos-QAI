# Operational verification scripts

Not part of the Python import path. Run from the repo root.

## verify_container.sh

Proves the app works inside the container: health, auth (401/200), training
delta of 10 steps, bind-mount write (learn_batch), persistence across restart,
zero published ports.

Requires: `docker compose`, `jq`.

```bash
export RESILEOS_TEST_KEY='...'
export RESILEOS_API_KEYS="{\"$RESILEOS_TEST_KEY\":{\"name\":\"bootstrap\",\"tier\":\"enterprise\",\"quota\":0}}"
bash scripts/ops/verify_container.sh
```

Exit 0 = all checks passed. Runs `chmod 666 titanos_live_state.json` in
pre-flight so the container can write to the bind mount.

## verify_tunnel.sh

Proves external traffic reaches the service through Cloudflare Tunnel with
zero published ports. Run only after `verify_container.sh` is green, and only
after `cloudflared tunnel create` has been run.

Requires: `docker compose`, `curl`, `jq`.

```bash
export TUNNEL_TOKEN='...'
export RESILEOS_TEST_KEY='...'
export RESILEOS_HOST='api.yourdomain.dev'
bash scripts/ops/verify_tunnel.sh
```

## bench_invention.py

Measures the three-tier epistemic model. The headline metric is the
**assertion rate on novel output**: how often does the system present
something it just invented as though it were a fact.

Requires: `requests`, a running API.

```bash
export RESILEOS_API_KEY='...'
export RESILEOS_BASE_URL='http://127.0.0.1:8000/api/v1'
# Optional LLM baseline:
export LLM_API_KEY='...'
export LLM_MODEL='gpt-4o-mini'
python scripts/ops/bench_invention.py
```

Writes `artifacts/report_invention.json`. Populates
`docs/benchmarks/invention-without-hallucination.md`.

## bench_compositional.py

Measures derivation rate on novel queries: does the system answer
`carol grandparent_of` when it knows `alice parent_of bob` and
`bob parent_of carol`. That is the composition mechanism; the invention
benchmark above measures the epistemic consequence.

Same requirements and environment. Writes
`artifacts/report_compositional.json`. Populates
`docs/benchmarks/compositional-generalization.md`.

Note: the composition path currently goes through `titanos.chain()`, not
through VSA `bind`/`unbind` operators on the query path. Label the table
"chain composition" until the operators are exposed.

## bench_vs_llm.py

Measures invent rate on unknown facts: how often does each system return a
fabricated answer for a fact it does not know.

Same requirements and environment. Writes
`artifacts/report_bench_vs_llm.json`. Populates
`docs/benchmarks/memory-vs-llm.md`.

## Note on zero-port deploys

With no published ports, these scripts cannot reach the API from the host.
Run them inside the container:

```bash
docker compose exec -T -e RESILEOS_API_KEY="$RESILEOS_TEST_KEY" \
  resileos python3 scripts/ops/run_ops_metrics.py --phase learn

docker compose restart resileos

docker compose exec -T -e RESILEOS_API_KEY="$RESILEOS_TEST_KEY" \
  resileos python3 scripts/ops/run_ops_metrics.py --phase verify
```

This is intentional: the auth perimeter is unreachable from outside the
container by design.
