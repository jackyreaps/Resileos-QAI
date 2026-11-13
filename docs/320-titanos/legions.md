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
| Hermes | Budget, depth, item limits. Paths and dispatch | Navigators, separated-cycle reviewers, Forge video, plan/test/debug | See full history. They get the artefact and the lesson |
| Hades | Lessons and checkpoints. Not Studio | Save, restore, fresh-context seeds, equal-budget baselines | Carry history or scars into the fresh packet |
| Apollo | Proof: success criteria, residual consistency | Outer verification and cleanup checks | Mark `verified` unless `verify_on_stop` passes |
| Eat / Perception | Ingest filters, `learn_fn`. The public name stays Eat | Structured ingest, including graphify | Write the residual store before the risk and budget gates |

`perception` is an alias of `eat`.

## Examples

`register_example_legions` registers nothing unless `enable=True`. The examples do not open a socket. Tests inject the functions and the files.

- Hermes `ollama_local` runs only when `confidence_route` returns `escalate_or_abstain`. The inference function is injected.
- Iris `jsonl_trace` reads a JSONL file. Hades `jsonl_trace` appends one JSON object. Neither is a vector store.
- Hades `lesson_notes` appends a line to a lesson file.
- Hermes and Apollo `action_placeholder` do not execute code. `risk_classify` still denies a hard-deny action. Only Apollo can set `verified`, and only through `verify_on_stop`.

This layer does not use LangChain, AutoGen, crewAI, or MetaGPT.

## Studio legions

`register_studio_legions` registers three tools. Each stays on one Kin.

- Hermes `forge_video` is the Forge video legion. Hephaestus is the Studio patron and is not a Kin, so the gate is Hermes. A matrix or residual packet is drafted and verified with the layer-scale studio codec (one scale on the rank-r product), phi-compressed below a native rank budget, and stepped with `KuramotoField` outward. That path accepts or rejects without a provider. Upscale stays off unless the residual check is inconclusive, and then it sends only the residual delta to a configured provider slot. A prompt with no residual input is a video request: with no provider the status is `UNAVAILABLE` and no URL is invented. The slot does not write residual facts. A worker process is a Clotho group and does not cross a Hades checkpoint.
- Eat `graphify` turns a graph or text into residual candidates and runs each through `eat_filter`. `learn` runs only for an accept when commit is set. The residual record is what a later question reads. Reject and abstain do not write.
- Hermes `plan_test_debug` plans, tests, and debugs. A repeated failure stops the loop. Lower-tier output stays out of the verified step. `write_file`, `apply_diff`, and `git_commit` stay refused until `verify_on_stop` passes. The HTTP route does not execute them.
- Hermes `dionysus` expands a prompt into synonym, root, and translation neighbours. Bind and bundle run in `latent_hub`, which is not Titanos. Hermes may use those neighbours to re-rank items the caller already supplied. Dionysus does not write a fact, and it is not a Kin. The tables are closed. This is not open-ended translation, coding, or general reasoning.

Morpheus is a summoned demi-god under Hades, not a legion and not a Kin. It replays logged turns and candidate branches on CPU, compresses a recurring pattern with the studio residual codec, and runs Hephaestus and Themis before Zeus may promote a triple. A candidate-only pattern is not promoted.

A Demi-god uses one of these only by naming it in the temporary swarm for its parent Kin.

## Code

`src/resileos/kin/legions.py`
