doc: RES-327-tools
title: Tool schemas and Human-Medium frames
status: stable
depends_on: [RES-327, RES-327-gate]
referenced_by: []

# Tool schemas and Human-Medium frames

External frontier mouths must not invent store facts. They call tools.

## 1. Tools

| Tool | Sector hint | Frame tag | Role |
|---|---|---|---|
| `resileos_ask` | gbx_like | operational | Single-hop exact |
| `resileos_chain` | otx_like | operational | Multi-hop path |
| `resileos_sparql` | otx_like | operational | Structured graph query |
| `resileos_abstain` | — | abstain | None-channel / refuse |
| `resileos_answer` | — | gnosis | Gate + mouth end-to-end |

Schemas: `src/resileos/answer/tools_schema.py`  
HTTP: `GET /api/v1/tools` returns OpenAI-style and raw schemas.

## 2. Frames (Human-Medium §10)

Frames are higher-order linguistic regulators: they bias which moves are
legible as true, safe, or anomalous. They are **not** enforced in code
yet; tags exist so operators can compare tool surfaces to suite docs
(e.g. `adjacent/gnosis_frame.md` in QD-TER-Human-Medium).

| Frame id | Intent |
|---|---|
| `operational` | Exact store ops; no interpretive overlay |
| `abstain` | Refusal / none-channel; matches syndrome zero |
| `gnosis` | High-coherence path through gate + mouth |

When you publish a frame note (Gnosis or other), map each frame clause
to one of: tool allow-list, sector policy, or recovery abstain. That
comparison stays documentary until you lock it in policy tables.

## 3. Policy (sector × path)

`src/resileos/answer/policy.py`

- `gbx_like` → prefer parent exact band; optional recurrent bypass
- `otx_like` → prefer Zeus first
- Zeus is **always invoked** when present; it may decline cheaply on
  `gbx_like` via `parent._route_sector` so fitness still updates

## 4. Fitness

Because Zeus always runs (and declines on gbx when configured),
`min_queries_before_eat` sees the full query mix, not only inverse/_of.
