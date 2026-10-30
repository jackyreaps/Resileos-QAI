doc: RES-327
title: Answer route and pluggable backends
status: stable
depends_on: [RES-320, RES-324, RES-326]
referenced_by: []

# Answer route (RES-327)

`POST /api/v1/answer` is the exact-retrieval + render path.

1. Resolve input: structured `subject`+`relation`, or free-text via
   `parse_query` then `encode_gate` (framework-native).
2. Unresolved -> `NONE_CHANNEL`.
3. Optional F2 recovery gate may `ABSTAINED`.
4. `ask_list` loads rows; backend renders one string.
5. Default backend for framework operation: `structured`.

See [gate-encoder.md](gate-encoder.md) for the gate/mouth contract.

## 1. Backends

Three backends, selected by `RESILEOS_ANSWER_BACKEND` (or by `auto`
fall-through: `local_hf` -> `hosted` -> `structured`).

| Backend | Needs | Cost | Accuracy on exact-match Q&A |
|---|---|---|---|
| `structured` | nothing | ~1ms CPU | 100% (renders `ask_list` directly) |
| `local_hf` | >=8 GB or GPU | ~200ms, 3 GB | see §2 |
| `hosted` | API key | ~500ms | not measured |

`structured` is the correct default for machine-consumed exact-match
queries. It renders the retrieved row verbatim; it cannot hallucinate.

## 2. RAG baseline (measured 2026-10-30, T4 GPU)

`run_rag_bridge_probe.py` on 24 exact-match queries from
`configs/titanos-facts.json`. Three conditions measured: store alone
(ceiling), model alone (parametric), model + store (RAG).

### 2a. Scaling curve

| Model | store alone | model alone | RAG strict | RAG permissive |
|---|---|---|---|---|
| Qwen2.5-0.5B base | 100% | 0% | 41.7% | ~42% |
| Qwen2.5-0.5B-Instruct | 100% | 0% | 41.7% | ~42% |
| Qwen2.5-1.5B-Instruct | 100% | 16.7% | 70.8% | **87.5%** |

*Strict* = exact string match. *Permissive* = substring plus
singular/plural tolerance (rescues `hunting` for `hunt`,
`Olympian deity` for `olympian`).

### 2b. Failure modes change with scale

**At 0.5B: prior override.** 14/14 failures returned wrong entities, not
verbose-correct answers. Examples: `Zeus domain -> Olympus`,
`sky domain -> Jupiter`, `primordial is_a -> Primordial`. The model
generates from pretraining priors and ignores the retrieved rows.
Instruction tuning made zero difference (0.5B-base and 0.5B-Instruct
both 41.7%).

**At 1.5B: verbose-correct dominates.** 4/7 failures were correct answers
rendered as prose (`hunting` for `hunt`, `messenger of the gods` for
`messengers`). Only 2/7 were prior override (`Apollo domain -> The
celestial sphere or sky`, `Uranus is_a -> planet`). A permissive matcher
recovers 87.5% at 1.5B.

### 2c. Deployment matrix

| Task | Backend | Accuracy | Reason |
|---|---|---|---|
| Machine-consumed exact match | `structured` | 100% | Renders retrieved rows verbatim |
| Human-facing prose, >=1.5B model | `local_hf` RAG | 87.5% | Acceptable paraphrase loss |
| Human-facing prose, <1.5B model | — | 42% | Priors override retrieval; do not deploy |

`structured` remains the correct default. RAG is opt-in for prose tasks
where a 12.5% paraphrase/drift rate is acceptable. Below 1.5B parameters,
RAG is not recommended: the model ignores its retrieved context.

## 3. Reproduce

```bash
# Structured backend (no model)
RESILEOS_ANSWER_BACKEND=structured uvicorn app:app
curl -X POST localhost:8000/api/v1/answer \
    -H 'content-type: application/json' \
    -d '{"subject":"Zeus","relation":"domain"}'

# RAG scaling probe (needs >=8 GB or GPU)
python scripts/run_rag_bridge_probe.py \
    --decoder Qwen/Qwen2.5-1.5B-Instruct \
    --out artifacts/report_rag_bridge_1p5b.json
```

## 4. Read next

- [Gate encoder contract](gate-encoder.md)
- [Path B mechanism](../300-substrate/pathb-mechanism.md) — RES-326
- [Zeus Child](zeus-child.md) — RES-324
- [Documentation Index](../readme.md)
