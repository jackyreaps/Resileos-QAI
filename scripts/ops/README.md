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

## Published tables (2026-11-10)

`docs/benchmarks/memory-vs-llm.md`, `compositional-generalization.md`, and
`invention-without-hallucination.md` record Resileos-only runs. The optional
model key was unset, so those tables have no model column filled in. Quote
the Resileos rows from those files. Do not add a comparison the run did not
make.

## bench_invention.py

Measures derivation rate and assertion rate on novel output: how often the
system presents a new fact as if it were stored. The candidate tier is not
on the query path. The 2026-11-10 run is in
`docs/benchmarks/invention-without-hallucination.md`
(`derivation_rate` 0.0, `invention_assertion_rate` 0.0, `p50_ms` 3.4).

Requires: `requests`, a running API.

```bash
export RESILEOS_API_KEY='...'
export RESILEOS_BASE_URL='http://127.0.0.1:8000/api/v1'
# Optional model hook. Leave unset. The 2026-11-10 tables did.
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

Measures invent rate on unknown facts for the Resileos API. The 2026-11-10
table left the optional model settings unset: exact-match 1.0 on 3 known
facts, invent rate 0.0 on 12 unknown pairs, p50 35.093815 ms.

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
