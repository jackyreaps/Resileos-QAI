---
doc: RES-608
title: leCore as Stomach (Gate + Digest Policy)
status: draft
depends_on: [RES-323, RES-605]
referenced_by: []
---

# leCore as Stomach (Gate + Digest Policy)

RES-605 defines the **outbound** HTTP bridge: Resileos calls leCore to
search capabilities and invoke tools. This document defines the
**policy** that turns leCore into a stomach: what may enter, how it is
routed, and that every successful external answer is digested into the
substrate rather than left as a one-shot HTTP result.

## 1. Metaphor → objects

| Metaphor | Object |
|----------|--------|
| Mouth | External models / tools advertised by leCore |
| Stomach / gatekeeper | `LeCoreClient` + policy in Resileos |
| Digestion | RES-323 ingest (φ-ladder, R-gate, Stream + Titanos.learn) |
| Memory | Titanos store |
| Specialist organ | Zeus child (RES-324), internal only |

## 2. Required loop

```text
query need outside store
        │
        ▼
LeCore search ──► ranked capabilities
        │
        ▼
policy allow? (budget, allowlist, rate limit)
        │
        ▼
LeCore invoke
        │
        ▼
RES-323 ingest(tokens or structured extract)
        │
        ├── StreamState (φ-weighted context)
        └── Titanos.learn (facts that pass extractor)
        │
        ▼
subsequent answers served from Titanos when possible
```

Hard rule: do not treat invoke as the final user-facing answer path for
durable knowledge. Invoke produces material to eat. Live one-shot tool
results (e.g. "what time is it") may skip learn but must be marked
non-persistent explicitly.

## 3. Policy knobs (operational)

| Knob | Purpose |
|------|---------|
| Allowlist of capability names | Limit which mouths may feed the system |
| Per-source / global rate limit | Avoid flooding ingest |
| Budget (invokes per session) | Cost control |
| Quality / R / CSI gates | Same family as RES-323; reject incoherent intakes |
| Mandatory ingest on text-like results | Default on for model outputs |

## 4. API surface (existing + recommended)

Existing (RES-605 / app.py):

- `GET /api/v1/lecore/health`
- `POST /api/v1/lecore/route` — search only today

Recommended addition (implementation not required by this draft):

- `POST /api/v1/lecore/invoke_and_ingest`
  - body: `{ "name", "args", "source_id", "ingest": true }`
  - returns invoke result and ingest summary (packets accepted, facts learned)

Until that exists, operators must call ingest after invoke in
application code.

## 5. Failure modes

| Failure | Behavior |
|---------|----------|
| leCore unreachable | Soft fail; Titanos-only path continues |
| Invoke error | `InvokeResult(ok=False)`; no ingest |
| Ingest rejects all packets | Log rejection reasons; store unchanged |
| Capability not allowlisted | Do not invoke |

## 6. Non-goals

- leCore does not own Titanos state
- leCore does not implement Zeus
- This doc does not change leCore's SERVICE.md; policy lives in Resileos

## 7. Status

Draft operational policy on top of stable RES-605 client.
