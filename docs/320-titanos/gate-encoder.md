---
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


## 1.1 Truth-frame system (four axes)

The encoder does not only resolve a triple. Together with gate state and
status it selects **what kind of truth claim** the answer is making.
GPU RAG probes (store accuracy 1.00 vs small-decoder RAG ~0.4) show the
failure mode is the model overriding retrieved rows — so the substrate
must own the frame and the model may only render.

| Axis | Values | Decides |
|---|---|---|
| Sector | `gbx_like` / `otx_like` | Exact band vs reconstructed path |
| Gate state | `LOCKED` / `REPULSE` / `MIXED` / … | Whether the field is coherent enough to trust |
| Status | `ANSWERED` / `NO_ROWS` / `ABSTAINED` / `NONE_CHANNEL` | What kind of answer is possible |
| Capacity | `log2|Σ|` | Bits the channel selection conveys |

**Derived `frame` field** (see `policy.derive_frame`):

| Frame | Typical axes |
|---|---|
| `exact` | gbx_like + ANSWERED + single row |
| `reconstructed` | otx_like or multi-row / path |
| `abstained` | ABSTAINED (recovery / field veto) |
| `unresolved` | NONE_CHANNEL or empty resolve |

`prefer_child` may use `gate_capacity_bits` below a floor to force the
parent/exact path (low-capacity gate → do not trust flexible or HF paths).

## 2. Sector policy

| Sector | When | Preferred path |
|---|---|---|
| `gbx_like` | Forward, non-`_of` attribute | Exact band: `ask_list` / parent Titanos |
| `otx_like` | Inverse or relational `_of` | Flexible: Zeus / chain when available |
| _(none)_ | Unresolved encode | `NONE_CHANNEL` — no rows, no prose invention |

Sector is a **routing label**, not a biological claim.

### 2.1 Fast-path contract

`/query` resolves a `gbx_like` forward query as follows:

- Call `titanos.ask_list(subject, relation, inverse=False)`
- If `len(rows) == 1`: build a synthetic `Answer` with `value=rows[0]`,
  `confidence=1.0`, `status="ACCEPTED"`, `mode="FAST"`, `loops=0`,
  `path=[(subject, relation, rows[0])]`, `gate_state="LOCKED"`, and
  `reason="gbx sector: exact retrieval, no recurrent pass"`
- Otherwise: `ans = None`, fall through to Zeus / recurrent

Three properties are load-bearing:

- **`len(rows) == 1` guard.** A gbx-labelled relation can turn out
  multi-valued in a given store. The guard protects against the case
  where a forward relation holds N > 1 objects. Returning a fake
  single answer here would be worse than falling through.
- **Zero rows falls through.** An empty band is not a fast-path
  success. The recurrent path abstains properly, producing a reason
  string and a confidence the caller can read.
- **Zeus is skipped on a successful fast path.** `mode="FAST"` and
  `loops=0` make this observable in the response.

### 2.2 Zeus scope and fitness coverage

Zeus is registered on the Titanos singleton's `AgencyGroup`, and
`stats()["agency"]` reflects it. On `/query`, Zeus is invoked for
`otx_like` sectors and for `gbx_like` queries that do not resolve to
exactly one row.

Consequence, stated here so it is not later mistaken for a bug:
**gbx fast-path answers do not contribute to Zeus's agency fitness.**
Zeus accumulates fitness on `otx_like` queries and on `gbx_like`
queries that fall through. If Zeus is ever pruned on otx-like
performance, it is being judged on a subset of its traffic.

Whether Zeus should be invoked on the fast path purely for fitness
accounting — paying the cost the sector exists to avoid — is an open
design question. See §8.

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
| `ABSTAINED` | Sigma-1 gate routed to ABSTAIN, or recovery gate veto (phase field) |
| `NONE_CHANNEL` | Gate unresolved (no subject/relation from text or vocab) |

`ABSTAINED` covers two distinct gates. The sigma-1 gate fires per
recurrent-loop step when its scar/volume conditions fail; the recovery
gate fires once after the recurrent loop completes when the phase field
cannot return to its synchron target. Both are recorded in the
`reason` field on the response.

`NONE_CHANNEL` is the operational form of the eighth syndrome outcome:
no channel selected, nothing written.

`/api/v1/answer` also returns:

| Field | Meaning |
|---|---|
| `symbol_index` | Index into live relation alphabet, or `-1` |
| `sector` | `gbx_like` / `otx_like` / `""` |
| `gate_capacity_bits` | `log2(|Σ|)` for the live relation alphabet (0.0 on none/abstain) |

That capacity number is the Part V §7.1 bound made operational.

## 5. Multi-valued relations on `/query`

`/query` returns a single `Answer.value`. For a relation with N objects
in the band, the recurrent path returns one of N — the one the loop
selected after `_quantum_sim` recovery when confidence falls between
the classical and abstain thresholds.

This is correct behaviour for a single-value endpoint, but it is
lossy by contract. To retrieve all N objects:

- `POST /api/v1/answer` — returns `rows: [...]`, every object in the band
- `POST /api/v1/sparql` — `SELECT ?o WHERE <s> --<r>--> ?o` returns rows

A caller that reads `"value": "Hestia", "mode": "QUANTUM_SIM"` from a
`Cronus --parent_of-->` query should read it as "the recurrent loop
survived on one of six," not "the ranked top-1."

## 6. Worked examples

On the 120-fact myth store:

| Question | Resolves to | Sector | Route |
|---|---|---|---|
| `What is Zeus's domain?` | `(Zeus, domain, False)` | `gbx_like` | fast path, 1 row → `mode="FAST"`, `loops=0` |
| `domain of Zeus` | `(Zeus, domain, False)` | `gbx_like` | same |
| `Who is the parent of Athena?` | `(Athena, parent_of, True)` | `otx_like` | Zeus → recurrent |
| `Cronus parent_of` | `(Cronus, parent_of, False)` | `otx_like` | 6 rows → recurrent, not FAST |
| `flurbo blorp quux` | `NONE_CHANNEL` | — | `symbol_index: -1`, abstain |
| `Zeus grandparent_of` | `NONE_CHANNEL` | — | relation not in `Σ`; abstain |

The last two rows are the same status by different paths: unknown
vocabulary in the first, unknown relation in the second. Both are
`NONE_CHANNEL`, both return `-1`.

## 7. Environment

Set `RESILEOS_ANSWER_BACKEND=structured` for the framework-native
gate/mouth spine. `auto` may still prefer `local_hf` if transformers is
installed; for pure framework deployment use `structured` explicitly.

## 8. Non-claims and open questions

**Non-claims.**

- Not a language model. The encoder matches against a closed
  vocabulary. It parses the phrasings in §6 and returns `None` on
  everything else. It does not generalise.
- Not a capacity measurement. `gate_capacity_bits` is a bound on the
  relation channel. Achieved capacity depends on the traffic
  distribution, which is not measured.
- Not a guarantee of single-valuedness. The sector label is a routing
  hint. The `len(rows) == 1` guard in §2.1 is what enforces the fast
  path, not the sector.
- Not a fallback encoder. `NONE_CHANNEL` does not degrade to a
  full-vocabulary cleanup. There is nothing to clean up; the gate
  produced no probe.

**Open questions.**

- Achieved vs bound capacity. The 2.81-bit bound (log2 of 7 relations)
  is theoretical. A measured distribution over resolved relations in
  real traffic would say whether the gate is being used efficiently.
- Zeus fitness coverage. §2.2 states the coverage gap. Whether Zeus
  should be invoked on the fast path purely for fitness accounting is
  a design question not settled here.
- Sector from cardinality. The sector is computed from the relation
  name (`_of` suffix, inverse flag), not from the band's cardinality
  at query time. Whether `gbx_like` should be decided by
  `len(ask_list) == 1` before the fast-path check, rather than after,
  is not decided.

## 9. API surface

- `POST /api/v1/answer` — exact retrieve + render; free-text uses `encode_gate`
- `GET  /api/v1/answer/backends` — availability
- `POST /api/v1/query` — recurrent path; `render=true` attaches `answer_text`
  via the same mouth; sector routes Zeus vs parent when agency is live

## 10. Tests

Run `pytest tests/test_native_encode.py tests/test_answer_backends.py -q`.

## 11. Read next

- [Answer backends](../320-titanos/answer.md) — RES-327
- [Zeus Child](../320-titanos/zeus-child.md) — RES-324
- [SDM + Hopfield Attractor Memory](sdm-hopfield.md) — RES-317
- [Documentation Index](../readme.md)
