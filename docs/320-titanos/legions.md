---
doc: RES-345-legions
title: Legions under Kin
status: implemented
depends_on: [RES-334-kin, RES-343-demigods]
---

# Legions under Kin

A Kin is a role class with constraints that do not move. A legion is one bounded tool registered on that Kin. It inherits the Kin's `risk_classify` gate, `evidence_attach`, and budget check. Callers reach it only through that Kin's catalogue. There is no global registry.

Legions serve under Kin. Kin serve under the residual core. A legion cannot take the residual core, bypass Zeus routing, cross the Hades checkpoint boundary, or turn the verified-cycle mouth on.

## Roles

| Kin | Persistent parameters | Legions may | Legions may not |
|---|---|---|---|
| Iris | Observation metrics, flags | Sensors, log readers, capacity probes | Write residual state |
| Metis | Policy rules, disable lists, mouth policy | Decision routers, risk classifiers, guide loaders | Execute. Output is policy only |
| Hermes | Budget, depth, item limits | Navigators, separated-cycle reviewers, blind verifiers | See full history. They get the artefact and the lesson |
| Hades | Checkpoint store, lesson, restart policy | Save, restore, fresh-context seeds, equal-budget baselines | Carry history or scars into the fresh packet |
| Apollo | Success criteria, residual consistency | Outer verification and cleanup checks | Mark `verified` unless `verify_on_stop` passes |
| Eat / Perception | Ingest filters, `learn_fn` | Structured ingest and perception helpers | Write the residual store before the risk and budget gates |

`perception` is an alias of `eat`.

## Examples

`register_example_legions` registers nothing unless `enable=True`. The examples do not open a socket. Tests inject the functions and the files.

- Hermes `ollama_local` runs only when `confidence_route` returns `escalate_or_abstain`. The inference function is injected.
- Iris `jsonl_trace` reads a JSONL file. Hades `jsonl_trace` appends one JSON object. Neither is a vector store.
- Hades `lesson_notes` appends a line to a lesson file.
- Hermes and Apollo `action_placeholder` do not execute code. `risk_classify` still denies a hard-deny action. Only Apollo can set `verified`, and only through `verify_on_stop`.

This layer does not use LangChain, AutoGen, crewAI, or MetaGPT.

## Code

`src/resileos/kin/legions.py`
