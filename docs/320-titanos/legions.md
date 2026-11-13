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

`register_studio_legions` registers the studio tools. Each stays on one Kin. The three scene stubs are registered with them.

- Hermes `forge_video` is the Forge video legion. Hephaestus is the Studio patron and is not a Kin, so the gate is Hermes. The legion compresses and checks. It does not generate video. A matrix or a two-frame phase step is drafted and verified with the layer-scale studio codec (one scale on the rank-r product), phi-compressed below a native rank budget, and stepped with `KuramotoField` outward. A supplied clip is different: frame 0 is a base packet and each later frame is a residual against the previous reconstruction (`src/resileos/studio/clip_codec.py`). A later frame whose temporal residual RMS is at or under 0.05 is marked `residual-consistent, reuse previous packet` and does not add a packet. A frame over that gate is a delta packet. That path accepts or rejects without a provider. Upscale stays off unless the residual check is inconclusive, and then it sends only the failing-frame residual deltas that also clear the sigma gate to a configured provider slot. A prompt with no frames and no packet is `UNAVAILABLE` and no URL is invented. The slot does not write residual facts. Stable Video Diffusion weights are not a production path and are not wired. A worker process is a Clotho group and does not cross a Hades checkpoint. A Hades checkpoint for a clip stores the lesson and the packet hash, and only after the sequence verifies. `VideoPacket` carries frame-residual hashes, the temporal delta, keyframe ids, the provider stage, and an optional scene-script hash. It does not carry a script.
- Hermes `daedalus`, `helios`, and `argus` are scene stubs under the same forge gate. Daedalus writes geometry, Helios writes lighting and materials, and Argus writes camera and animation. Each hashes its artifact and checkpoints through Hades. Restore starts from the lesson and the residual hash. The classical core sees that hash, not the script. No Blender executor is configured. See the naming table below.
- Eat `graphify` turns a graph or text into residual candidates and runs each through `eat_filter`. `learn` runs only for an accept when commit is set. The residual record is what a later question reads. Reject and abstain do not write.
- Hermes `plan_test_debug` plans, tests, and debugs. A repeated failure stops the loop. Lower-tier output stays out of the verified step. `write_file`, `apply_diff`, and `git_commit` stay refused until `verify_on_stop` passes. The HTTP route does not execute them.

## Naming

| Tool | Kin | Job | Named for |
|---|---|---|---|
| `forge_video` | Hermes | Compress and check a supplied still or clip. Does not generate video. | The forge, under Hephaestus. The tool name is unchanged. |
| `daedalus` | Hermes | Scene geometry stub. Writes an artifact and a residual hash. | Daedalus, the craftsman. |
| `helios` | Hermes | Lighting and materials stub. | Helios, the sun. |
| `argus` | Hermes | Camera and animation stub. | Argus, the many-eyed watcher. |
| `graphify` | Eat | Ingest a graph through `eat_filter`. | Not a god name. The public tool name stays `graphify`. |
| `plan_test_debug` | Hermes | Plan, test, and debug. | Not a god name. The public tool name stays `plan_test_debug`. |

No existing public API was renamed. A name already in use stays, and these three were checked against the Kin and legion names on this tree before they were added.

A Demi-god uses one of these only by naming it in the temporary swarm for its parent Kin.

## Code

`src/resileos/kin/legions.py`
