# Harness Integration Checklist

Wires the harness layer (AgenC session/risk, Jev cascade, Harness
Engineering patterns) into the Kin cycle, the residual `Packet`, the
leCore surface, and `/api/v1/tools`.

The residual core stays untouched. Harness state lives on an attached
`ControlPacket` that travels with every Kin cycle and tool call.

## Prerequisites

The following must exist on `main` before this integration will import:

- `src/resileos/harness/__init__.py`
- `src/resileos/harness/packet.py` with `ControlPacket`
- `src/resileos/harness/tools.py` with:
  `decision_fanout`, `confidence_route`, `risk_classify`,
  `verify_on_stop`, `budget_and_stuck_guard`, `guide_load`,
  `evidence_attach`, `residual_consistency`, `apollo_success`
- `src/resileos/harness/cascade.py` with `CascadeRouter`
- `docs/harness/AGENTS.md`
- `docs/harness/CONSTRAINTS.md`
- `configs/harness_policy.yaml`

If any are missing, the harness package must be created first. The
Kin cycle cannot import partial dependencies.

## Order of operations

1. Verify `pytest tests/test_harness*.py -q` passes on `main` before
   touching `bundle.py`. If the harness package has no tests, add
   `tests/test_harness_tools.py` before integration. Integration without
   a baseline means every subsequent failure is ambiguous.

2. Replace `src/resileos/kin/bundle.py` with the harness-integrated
   version. The `cycle()` method gains three behaviors:
   - Budget + stuck guard at the top (early return on failure, marked
     `verified: False`)
   - Residual consistency sensor if a residual `Packet` is supplied
   - Apollo outer verification via `verify_on_stop`

3. Replace the `/api/v1/kin/cycle` handler in
   `src/resileos/kin/http_routes.py` to accept the optional
   `residual_packet_hash` and pass it through as a stub.

4. Update `/api/v1/tools` in `app.py` to expose `HARNESS_TOOLS` alongside
   the existing tool schemas.

5. Run `pytest tests/test_harness_integration.py -q`.

6. Verify endpoints:
   ```bash
   curl -s http://127.0.0.1:8000/api/v1/tools | jq '.harness'
   curl -s -X POST http://127.0.0.1:8000/api/v1/kin/cycle \
       -H 'content-type: application/json' \
       -d '{"metrics": {"hits": 10, "misses": 1}}' | jq '.harness'
   ```

## What travels with the cycle

Every `KinBundle.cycle()` call attaches a `ControlPacket` that
accumulates:

- `guides_loaded` — guides loaded this cycle (JIT context)
- `budget_remaining` — remaining budget after guard check
- `verified` — set by `verify_on_stop` at the end
- `evidence` — residual hashes and any other attached evidence

The `harness_summary` returned from `cycle()` contains
`verified`, `consistency`, `apollo`, `budget`, `guides`. Downstream
callers should gate on `harness_summary["verified"]` before treating
the cycle's output as authoritative.

## What this does NOT do

- Does not change the residual `ResidualCore` contract.
- Does not change the `Packet` schema (RES-201).
- Does not change Zeus routing or the agency fitness rules.
- Does not mount `/api/v1/world/*` or `/api/v1/guild/*`.

## Rollback

If the integration breaks a downstream consumer, revert
`src/resileos/kin/bundle.py` to the pre-integration version. The
`ControlPacket` attachment is additive on the `KinBundle` dataclass;
removing the `control` field and the three harness blocks in `cycle()`
returns the bundle to its previous behavior. `HARNESS_TOOLS` in
`app.py` is independent and can be removed separately.
