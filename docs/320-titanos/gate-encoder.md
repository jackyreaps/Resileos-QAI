doc: RES-327-gate
title: Gate Encoder and Dual-Sector Mouth
status: stable
depends_on: [RES-327, RES-324]
referenced_by: [RES-327]

# Gate Encoder and Dual-Sector Mouth

Framework-native free-text path for Titanos. No external LLM and no
HuggingFace decoder on the encode side. Language selects a discrete
channel against the live store vocabulary; the mouth renders residue
only — it never invents rows.

## 1. Encoder: `encode_gate`

Module: `src/resileos/answer/native_encode.py`

Input: free-text question plus live `entities` and `relations` from the
Titanos singleton.

Output: `GateSelection` or `None`.

| Field | Meaning |
|---|---|
| `subject`, `relation`, `inverse` | Store triple |
| `symbol_index` | Index of `relation` in the live relation alphabet Σ |
| `gate_capacity_bits` | `log2(|Σ|)` — bits conveyed by the gate per use |
| `sector` | `gbx_like` (rigid exact band) or `otx_like` (flexible / inverse / path) |
| `pattern_kind` | Which surface pattern matched |

`None` means unresolved: no channel selected. Routes treat that as the
**none channel** (`status: NONE_CHANNEL`), not as a guess.

`encode_question(...)` is a thin wrapper that returns only the triple
(or `None`) for older call sites.

## 2. Sector policy

| Sector | When | Preferred path |
|---|---|---|
| `gbx_like` | Forward, non-`_of` attribute | Exact band: `ask_list` / parent Titanos |
| `otx_like` | Inverse or relational `_of` | Flexible: Zeus / chain when available |
| _(none)_ | Unresolved encode | `NONE_CHANNEL` — no rows, no prose invention |

Sector is a **routing label**, not a biological claim.

**Zeus scope (Tier A).** `/query` always invokes Zeus when registered.
Zeus declines cheaply on `gbx_like` (via `parent._route_sector`) so
fitness tracks the full query mix. Parent exact-band path handles
`gbx_like` after decline. Optional fast path: unique `ask_list` row
skips long recurrent loops on `gbx_like`.


## 3. Mouth: `StructuredBackend`

Same backend for `/api/v1/answer` and `/api/v1/query?render=true`.

- Renders only retrieved rows / `Answer.value` / `Answer.path`
- Annotates loop depth, non-LOCKED `gate_state`, and sector when present
- On exception, falls back to structured again — never to a generative invent

## 4. Status values

| Status | Meaning |
|---|---|
| `ANSWERED` | Rows present, prose rendered |
| `NO_ROWS` | Triple resolved, store empty for that pair |
| `ABSTAINED` | Recovery gate veto (phase field) |
| `NONE_CHANNEL` | Gate unresolved (no subject/relation from text or vocab) |

`NONE_CHANNEL` is the operational form of the eighth syndrome outcome:
no channel selected, nothing written.

`/api/v1/answer` also returns:

| Field | Meaning |
|---|---|
| `symbol_index` | Index into live relation alphabet, or `-1` |
| `sector` | `gbx_like` / `otx_like` / `""` |
| `gate_capacity_bits` | `log2(|Σ|)` for the live relation alphabet (0.0 on none/abstain) |

That capacity number is the Part V §7.1 bound made operational.


## 5. Environment

```bash
export RESILEOS_ANSWER_BACKEND=structured   # framework-native default
```

`auto` may still prefer `local_hf` if transformers is installed; for the
gate/mouth spine use `structured` explicitly.

## 6. API surface

- `POST /api/v1/answer` — exact retrieve + render; free-text uses `encode_gate`
- `GET  /api/v1/answer/backends` — availability
- `POST /api/v1/query` — recurrent path; `render=true` attaches `answer_text`
  via the same mouth; sector routes Zeus vs parent when agency is live

## 7. Tests

```bash
pytest tests/test_native_encode.py tests/test_answer_backends.py -q
```
