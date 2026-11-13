---
doc: RES-346
title: Component inventory
status: draft
depends_on: [RES-200, RES-201, RES-334-kin, RES-338, RES-343, RES-345]
referenced_by: [RES-000]
---

# Component inventory

Read of Kin, demi-gods, Hermes paths, legions, swarms, and the studio / chat / mouth / oscillator / residual-cascade modules on this tree. Zeus is Core, not a Kin. Eat keeps the name Eat. Harmonia sits under Hermes, not as a Kin. Hephaestus is Forge patronage, not a Kin.

This is a code reading. It does not claim a production video path, a photograph metric, or a comparison with another model. Digit-study PSNR in the studio research note is an 8×8 digits figure. It is not photo quality and it is not video quality.

Base for the reading: `main` includes squash-merged PR #25 at `b1220370`, PR #26 at `531595ca`, PR #27 at `a640101`, and the inventory at `b78e89b`. `src/resileos/ui/residual_frame.py` is on this tree.

## Language draft, verify, render

Chat and query now follow the same shape as `forge_video`: draft a line, verify it, then keep or drop the write. This does not add open-ended generation, fluent coding, or general reasoning. The residual core is still not a sampler. A fast sentence is not a stored fact.

| Piece | What it does | What it does not do |
|---|---|---|
| Candidate query | `Titanos.ask` / `chain` return `CANDIDATE` when an exact close fails and a stored signal remains: residual nearest neighbour of a multi-valued slot, hypervector similarity on that neighbour, or a partial chain hop. `value` stays null. `unverified` is true. The mouth says the closest match is unverified. | It does not learn. An unknown entity, a relation with no facts, and an empty slot stay `ABSTAINED`. Exact `ACCEPTED` rows are unchanged. |
| Fast route | Iris `classify_intent` sends a greeting, small talk, a meta question, or a line with no factual claim to the persona mouth. Themis, Momus, and Atlas are not consulted on that path. `verified` is false, `source` is `conversational`, and the line changes with the wording. | A stored value, `remember` / `learn`, `write_file`, `apply_diff`, `git_commit`, or a `/tool` or `/search` still runs the Kin cycle. `require_verified` stays true for factual lines. |
| Deferred review | `schedule_review` runs a SeparatedCycle on a thread after the reply object exists. A rejected review does not call `learn`. A teach that reports `wrote` still waits so the flag matches the review. | No new queue service. Nothing is written before reviewers pass. |
| Conflict and abstain lines | `custom_mouth` / `language_codex` name the rows and their time windows. No model call. | They do not pick a winner and do not store one. |
| Dynamic Hermes budget | Metis widens `max_depth` / `max_items` for a multi-hop question and keeps a simple lookup tighter, inside Hephaestus caps (depth 4, items 16). `clip_hops` is what changes chain work. | `Titanos.chain` itself is not clipped. Exact M5 chains still walk the hops the caller passed. |
| Morpheus | Demi-god under Hades. Replays logged turns and candidate branches, compresses a recurring pattern with the studio codec on CPU, then Hephaestus and Themis. Promotion is `zeus_head`. An optional `backend(matrix)` may replace the codec. | No GPU. No training framework. A candidate-only pattern is not promoted. Visual paths still do not call `learn` or update a scar matrix. |
| Dionysus | Legion under Hermes, not a Kin. Expands synonym, root, and translation neighbours with `bind` / `bundle` into `latent_hub`. Hermes may re-rank items it was already given. | It never writes Titanos. The tables are small and closed. This is not a translator model. |
| Latent hub | `src/resileos/latent_hub.py`. Hypervectors and consolidated patterns, apart from Titanos. | Not a fact store. Not a scar matrix. |

## What this change wired

Visual quantizers were calling `ResidualCore.step`, which updates that core's scar matrix `Lambda`, after the stack had already been factorized.

- `encode_frame` / `encode_clip` (`src/resileos/ui/frame_codec.py`) now keep `_factorize_residual_stack` and hash that stack. They do not call `step` or `_scar_update`. `scar_matrix_updated` and `learned` are false. The hash is a digest of the factors and scales. It is not a RES-201 packet.
- Studio stills, image / video / language / audio perception, the local pattern helper, video-codex recesses, `diagnose_with_scale`, the scale-wire helpers, and the query-response address call `scale_address(..., step_core=False)`. That address does not step a core. The still's quantizer remains the layer-scale studio codec in `scripts/studio/codec.py`.

`step_core` stays true for addresses that are not a frame: Eat decisions, council, art titles, hub addresses, and the mouth's scale tag. Those still build a throwaway 4×4 core inside `core_step_from_address`. Chat `turn_residual` still calls `core_step_from_address` after language perception. `query_scale.with_scale` still calls `step_shared`, which steps a process-wide 4×4 core. Those two were left in place.

Samples stay candidates. No visual path calls `learn`.

## Left out, and why

| Item | Why it stayed out |
|---|---|
| `suite_residual` label (`r{luma}{edge}_s{belt}`) | The function only receives two scalars and a belt. Replacing it with a core residual would invent a matrix. Eat, chat, and council addresses still use this label. The env hook `RESILEOS_RESIDUAL_IMPL` remains the override. |
| `LearnedConvCodec` | `encode_matrix` and `decode` raise `CodecUnavailable`. Training a conv encoder is a separate model, not a fill-in from the current stack. |
| Lachesis `measure` and Harmonia `route` on the live cycle | Both functions exist and are tested. Nothing in `src/` calls them. Chat reuses the control id `chat-turn`, and the kin bundle reuses `kin-bundle`, so a shared-step route keyed by that id would not see a second cycle. A gain-versus-cost number for `measure` is not defined on the cycle. Wiring a made-up gain would be a new policy. |
| Nike on `apollo_cycle`, Themis inside `plan_test_debug` | `nike_check` fails when the lesson has no explicit criterion line. The plan loop's "themis" role is the existing mutate refusal (`verify_on_stop`), and the loop does not build a Hades lesson. Calling the checks without those inputs would fail closed for a reason the caller did not supply. |
| Rheology coordinates and the canonical metric-bridge head | `NotImplementedError` by design until the coordinate system in RES-601 is derived. Not a studio shell. |
| External samplers and video providers | Slots stay off. Unconfigured calls return unavailable and do not invent a URL. Higgsfield, Seedance, ComfyUI, OpenAI, Kapwing, vidful.ai, aifreevideo.com, and Stable Video Diffusion are not wired. Official SVD weights are research-licensed and are not a path for this product. |
| A residual-gated video page | Left out of PR #28. This tree now has `GET /studio/video` and the Streamlit Video tab. See "Video surface". |
| Clip-level temporal residual tracking | Left out of PR #28. This tree now has `src/resileos/studio/clip_codec.py`. See "Temporal residual clip". |
| PR #27 | Squash-merged to `main` at `a640101`. `src/resileos/ui/residual_frame.py` is on this tree. |

## Residual core and packets

| Piece | Path | What it does | Facts / Zeus | Native or wrapper | Next increment |
|---|---|---|---|---|---|
| Residual core | `src/resileos/core.py` `ResidualCore.step` | Deterministic bipolar low-rank stack on a matrix `W` the caller already has. Updates `Lambda`, emits a RES-201 `Packet` (layer 0 factors). Does not sample pixels and does not read a prompt. | The scar update is inside the core. It does not call Titanos `learn`. | Residual-native. Real. | Keep studio and perception off `step`, which this change does for those paths. |
| RES-201 packet | `src/resileos/packet.py` | Layer-0 factors, scales-as-exponents, `Lambda`, hash. A packet alone cannot rebuild the matrix. | Carries the scar. It is not a store write. | Residual-native. Real. | Leave the schema frozen. |
| Control packet | `src/resileos/harness/packet.py` `ControlPacket` | Harness overlay: confidence, risk, verified, evidence, scars, guides. | Holds evidence. A write still needs a learn path. | Residual-native harness. Real. | — |
| Studio codec | `scripts/studio/codec.py` `encode` / `decode` | Same factorization family, one scale per layer or per component, packed as `studio-codec/1`. Decode is the sum of the layers. Does not call `step`. | No learn. No shared `Lambda`. | Residual-native. Real. | — |
| `res201_layer0_product` | same file | Comparison helper. This one does call `step`, to show what the RES-201 packet omits. | Local core only. Not the studio encode path. | Measurement. Real. | Keep it out of request handlers. |
| PCA codec | `src/resileos/studio/codecs.py` `PcaComponentCodec` | 8×8 digits bases, per-component scales. | `learned` false. No `step`. | Residual-native on a digits prior. Real, narrow. | Do not quote its PSNR as photo or video quality. |
| Learned conv codec | same file `LearnedConvCodec` | Raises `CodecUnavailable`. | No. | Stub. | Leave until a conv model exists. Selecting it returns 409 from the studio route. |

## Kin

Zeus is Core. The Kin are Iris, Metis, Hermes, Hades, Apollo, Athena, Eat, Psyche, and Aphrodite.

| Name | Path | What it does today | Writes facts or bypasses Zeus? | Native or wrapper | Next increment |
|---|---|---|---|---|---|
| Zeus | `src/resileos/titanos/zeus.py` | Agency child. Declines on a low field-R or a bad hop, otherwise `ask` / `chain`. Does not learn. Mode B carrier prose is off. | Cannot write. The learn gates are elsewhere (Eat route, separated apply, graphify commit). | Structured reader. Real, narrow. | One learn choke-point is a later change. This pass does not merge the gates. |
| Iris | `src/resileos/kin/iris.py` | `observe` copies hits, misses, teaches, sessions, hit rate, and agency children into `IrisReport`. `classify_intent` labels a turn before the cycle. Handler returns `None`. | No store write. | Metrics observer plus an intent label. Real, narrow. | A fast label skips the cycle. It does not answer a fact. |
| Metis | `src/resileos/kin/metis.py` | `organize` sets `prefer_structured`, `allow_mouth` (false until hit rate and hit count clear the bar), depth cap, and `disable_children`. `hermes_budget_for` widens depth and items for a multi-hop line and keeps a simple lookup tighter, inside the Hephaestus caps. Handler answers `sys:agency` policy/status only. | No world learn. Can mark an agency child inactive. | Policy. Real, narrow. | The cap is a bound on Hermes. It is not a longer exact chain inside `Titanos.chain`. |
| Hermes | `src/resileos/kin/hermes.py` | `navigate` ranks and truncates caller-supplied items. It does not invent triples. Handler returns `None`. | No. | Residual-map navigator. Real, narrow. The handler is a decline. | Chat history and lesson windows call `navigate`. `KinBundle.cycle` stores it and does not call it. |
| Hades | `src/resileos/kin/hades.py` | File checkpoints under `data/hades/`. `save` does not check `verified`; the caller does. `restore_fresh` drops history, evidence, and scars, sets `verified` false, and appends the lesson. It also copies guides, budget, confidence, and risk class. The file itself still stores scars and an evidence gist. | No Titanos learn. | Residual-native checkpoint. Real. | A strict mode that refuses an unverified `save` would change Echo and any caller that saves first and verifies later. Not done here. |
| Apollo | `src/resileos/kin/apollo.py` | Golden-ladder hops. `eat_fn` can reject a hop unless `art=True`. Healing constant is 39.5. `predict_next` proposes the following weight. In the kin bundle, Apollo is the `apollo_success` status dict, not this hopper. | Separated cycle can learn after reviewers. The hopper writes only if the caller passes a real `eat_fn`. | Ladder is residual-native. The bundle sensor is a status check. Real, two different jobs. | Do not treat the status dict as the hopper. |
| Athena | `src/resileos/kin/athena.py` | Builds a short reading from perception addresses and drives, then `gate_candidate`. | In the separated perception path the reading can become a claim for Zeus. | Summarizer. Thin, real. | The studio plan loop calls `judge` once at the end on a pass/fail bin. |
| Eat | `src/resileos/kin/eat.py` | Parses a triple, runs the verifier pipeline, returns accept / reject / abstain. `eat_and_learn` calls the injected `learn_fn` on accept. | `POST /api/v1/eat` calls `titan.learn` after verifiers. That route does not go through `zeus_head`. Preview does not learn. | Filter is residual-native. The HTTP learn path is a direct store write. Real. | Pointing this route at `zeus_head` would change who may write. Left as a documented difference. |
| Psyche | `src/resileos/kin/psyche.py` | In-memory phase, belt, residual bin, persona, frames, drives. `hub_rows` shapes triples. | Those rows are not learned unless a caller submits them. | State holder. Real. | — |
| Aphrodite | `src/resileos/kin/aphrodite.py` | Preferences, tutorial steps, and persona stage in `data/aphrodite/<hub>.json`. Fact handler declines. `writes_residual` is false. | No residual facts. Preferences are a side file. `advance` on the HTTP state route accepts the client's `verified` flag. | Preference store. Real for that job. The fact handler is a decline. | The client `verified` flag is an honesty gap on tutorial advance. Not changed here, and not a mouth-policy edit. |

`KinBundle.cycle` (`src/resileos/kin/bundle.py`) runs guide load, budget guard, Iris, Metis, `residual_consistency`, `apollo_success`, `verify_on_stop`, and a Hades checkpoint when the turn is verified and `checkpoint_allowed` says the owned group is stopped. It imports `CascadeRouter` and does not call it. Confidence routing for stills lives in the studio cascade, not in this cycle.

## Demi-gods

Summon loads one capped guide into the caller's control packet. The Python check is the decision. Dismiss drops the guide. None of the checks call `learn`. `src/resileos/kin/demigods/`.

| Name | Check | What it does | Facts / Zeus | Class | Next increment |
|---|---|---|---|---|---|
| Themis | `themis_check` | Passes when residual consistency, Apollo success, and a Hades lesson with `verified=true` agree, and evidence is present. | No. | Real. | Studio `gate_studio_packet` already calls it for component packets. The plan loop does not. |
| Momus | `momus_review` | Blind to history and author notes. Checks explicit requirements and a 64-hex residual hash. No requirements yields `need_more`, which is not approval. | Approved Momus can reach `zeus_head` inside `maker_blind_verifier_cycle`. | Real. | The plan loop calls Momus only when `spec` and `residual_hash` are both passed. Otherwise the critique is a local pass/fail note. |
| Hephaestus | `hephaestus_check` | Residual consistency, empty scars, budget guard, and an optional Hermes budget. Patron of Forge. Not a Kin. | No. | Real. | The studio cascade calls this on the still packet. |
| Nike | `nike_check` | Explicit criteria, each backed by Apollo success or residual consistency. No criterion line fails. | No. | Real, and unused on the Apollo writer. | Call it only when the caller actually supplied criteria. |
| Atlas | `atlas_check` | Declared loads against `check_capacity` / hopfield cap, mask stack, prime tower, primorial count, and `EVIDENCE_CAP`. Undeclared loads are not invented. | No. | Real. | The kin cycle does not put declared loads on the packet, so Atlas has nothing to hold unless the caller passes them. A fast chat turn does not call Atlas. |
| Morpheus | `morpheus.py` `run_idle` | Replays turns, compresses a recurring pattern with the studio codec, then Hephaestus and Themis. Zeus promotes. | Learn only through `zeus_head` after those checks. | Real CPU pass. Optional backend hook. | Not a dream model. A candidate branch is not promoted. |

`demigod_summon` / `dismiss` and `demigod_attempt` are real. A swarm name must already be a legion on the parent Kin (Themis and Nike under Apollo, Momus and Hephaestus under Hermes, Atlas under Iris) or a check-local helper. The mount is temporary. Clotho notes a process group; Atropos cuts it on dismiss. Hades still waits for a fully stopped group.

## Hermes paths (Moirai)

`src/resileos/kin/moirai.py`. Not a separate Kin.

| Name | What it does | Called from production paths? | Facts / Zeus | Class | Next increment |
|---|---|---|---|---|---|
| Clotho | Registers a process group or a cancel callback. | Yes. `reserve_spawner`, `note_worker`, demigod swarm, and the kin-cycle stop path. | No. | Real. | — |
| Lachesis | `measure` expands only when expected gain is greater than cost. `note` stores a cycle id, packet, and residual hash. | No. Tests only. | No. | Real function, unwired. | Needs a defined gain and a cycle id that is unique per attempt. |
| Atropos | `cut` sends SIGTERM then SIGKILL to an owned group that is not the caller's group. `stop_requested` and `fully_stopped` differ. | Yes. `cut_owned`, `stop_owner`, swarm dismiss. | No. | Real. | — |
| Harmonia | `route` shares a step when hash or packet-prefix overlap is at least 0.8. `certify` accepts that share only when residual consistency and `verify_on_stop` both hold. | No. Tests only. | No. | Real function, unwired. | Same id-collision note as Lachesis. |
| `checkpoint_allowed` | Hades may record after a stop only when consistency holds and the group is fully stopped. | Yes, from `KinBundle.cycle`. | Gates a checkpoint. Does not learn. | Real. | — |

## Legions

`register_legion` (`src/resileos/kin/legions.py`) hangs one tool on one Kin. The wrapper runs `risk_classify`, the budget guard, and `evidence_attach`. It refuses `residual_core`, `bypass_zeus`, `bypass_hades`, and `bypass_mouth`. `learn_fn` is stripped unless the Kin is Eat and the risk class is `allow`.

Registered when the app process starts (`app.py` `_register_runtime_legions`):

| Legion | Kin | What it does | Facts / Zeus | Class | Next increment |
|---|---|---|---|---|---|
| `web_search` | Hermes | Posts the query to the DuckDuckGo HTML endpoint and parses result anchors. | No residual write. | Wrapper around that site. Real when the network call works. | Keep it off the residual store. Failures return `ERROR` and an empty result list. |
| `forge_video` | Hermes | Compresses and checks a supplied matrix, a frame pair, or a clip. A clip is one base packet plus delta packets for frames whose temporal residual RMS is over 0.05. Frames at or under that gate reuse the previous packet. `produces_video` stays false. It does not generate video. A prompt with no frames and no packet is `UNAVAILABLE` and `url` is null. Upscale runs only after an inconclusive residual, and only if a provider slot is set. | The wrapper strips `learn_fn` and `bypass_zeus`. The cascade raises if those are passed. The clip path does not call `ResidualCore.step`. | Residual-native for frames that already exist. The prompt-only branch is an optional provider slot, off by default. | Do not point the empty slot at a hosted video product. Stable Video Diffusion weights are not a path. |
| `daedalus` | Hermes | Scene geometry stub. Writes an artifact and a residual hash, then a Hades checkpoint. | No residual write. The classical core sees the hash only. | Stub. No Blender executor. | Leave it a stub until an executor exists. |
| `helios` | Hermes | Lighting and materials stub. Same checkpoint boundary as Daedalus. | No residual write. | Stub. | Same as Daedalus. |
| `argus` | Hermes | Camera and animation stub. Same checkpoint boundary as Daedalus. | No residual write. | Stub. | Same as Daedalus. |
| `graphify` | Eat | Parses edges, runs `eat_filter`, and records a residual candidate hash. `commit` plus an allow risk can call `learn_fn`. | Writes only through the Eat legion gate. | Residual-native. Real. | — |
| `plan_test_debug` | Hermes | Budgeted plan / test / debug. `write_file`, `apply_diff`, and `git_commit` stay refused until `verify_on_stop` passes and `allow_mutate` is set. The HTTP route does not execute them. | No learn. | Real loop. The role labels `themis: "law"` and `hades: "lessons"` do not call `themis_check` or `Hades.save` (`checkpoint` is null). | Leave the labels honest in this inventory rather than calling checks that lack a lesson. |
| `dionysus` | Hermes | Expands synonym, root, and translation neighbours into the latent hub and can re-rank items Hermes already has. | No Titanos write. | Real closed tables plus bind/bundle. | Not a translation model. |
| `calliope`, `ligeia`, `echo` | Aphrodite | Suggestion, cue, and an optional lesson. `writes_residual` is false. Echo can `Hades.save` a lesson with `verified` false when asked. | No residual facts. | Real, narrow. | — |

`register_example_legions` returns nothing unless `enable=True`. The examples (`ollama_local`, `jsonl_trace`, `lesson_notes`, `action_placeholder`, `restore_fresh`) stay off. `ollama_local` runs only an injected function, and only when confidence routing says escalate. `action_placeholder` does not execute code.

Importing the library registers nothing until `register_*` runs.

## Swarms and SeparatedCycle

| Piece | Path | What it does | Facts / Zeus | Class |
|---|---|---|---|---|
| Verifier pipeline | `src/resileos/kin/verifiers.py` `run_verifiers` | Nine deterministic checks. `eat_filter` uses it by default. | Accept / reject / abstain only. | Real. The name `use_swarm` is this pipeline, not the demigod swarm. |
| Demigod swarm | `src/resileos/kin/demigods/swarm.py` | One summon, temporary legion names, Clotho on spawn, Atropos on stop. | Refuses `learn_fn`, Zeus, and bypass flags. | Real. |
| SeparatedCycle | `src/resileos/harness/separated.py` | Writer gets a capture shim, not `learn`. Reviewers are verifiers, council, and optional Athena. `zeus_head` calls `learn_fn` only when every reviewer approves. | This is the Zeus write gate. | Real. |
| `maker_blind_verifier_cycle` | same file | Maker, then Momus on a separate packet, then Zeus. `need_more` does not approve. One supplement round. | Learn only on Momus approval. | Real. |
| Cascade router | `src/resileos/harness/cascade.py` | Fans a multiple-choice question out over residual rows already on the packet, then `confidence_route` and `verify_on_stop`. The default residual abstains when those rows are missing. | No learn. | Real policy. Constructed in tests. The kin cycle does not call it. |

`confidence_route` (`src/resileos/harness/tools.py`): at or above 0.99 the route is residual or Apollo; at or above 0.7 it is cascade; otherwise escalate. The studio still judge uses the same helper. High confidence does not invent a row.

## Studio, chat, mouth, oscillator

| Module | Path | What it does | Facts / Zeus / scars | Class | Next increment |
|---|---|---|---|---|---|
| Residual cascade | `src/resileos/studio/residual_cascade.py` | Layer-scale codec, outward Kuramoto order, Hephaestus, residual consistency, confidence route, Apollo status. Accepts, rejects, or leaves the still inconclusive. `produces_video` is false. Energy is relative residual energy, not digit PSNR. | `_refuse_bypass` on `learn` and `bypass_zeus`. `remember_accepted` is a 256-entry RAM index, not Titanos. Scale address no longer steps a core. | Real for a still candidate. | Clip residuals live in `clip_codec.py`. This module still owns the still and the two-frame phase step. |
| Candidates | `src/resileos/studio/candidates.py` | In-memory id. `learn` arguments are ignored. | No. | Thin, real. | A restart drops the id. Persistence would be a new store. |
| Gate | `src/resileos/studio/gate.py` | Hephaestus, consistency, and Themis on a component packet. | `scar_matrix_updated` false. | Real. | — |
| Routes and service | `src/resileos/studio/routes.py`, `service.py` | Round trip, toy prior, gate, forge, graphify. Graphify `commit` can learn. External sampler returns 403 when off. | Codec paths do not learn. | Real. | — |
| External sampler | `src/resileos/studio/external_sampler.py` | Default off (`DisabledExternalSampler`). `fake` builds a local packet. `minimax_api` needs a key and a base URL; a returned image is re-encoded. No URL is fetched from the response. | No learn. | Off by default. | Leave the slot off. |
| Panel | `src/resileos/studio/panel.py`, `ui_studio.py` → `src/resileos/ui/studio_app.py` | Streamlit studio. The codec panel shows the round trip and says the 8×8 figure is not a photograph. | Perception does not learn. | Real UI over the codec. | A video surface would be a sibling of this panel. See below. |
| Oscillator | `src/resileos/substrate/oscillator.py` `KuramotoField` | CPU Kuramoto step, outward depth. The cascade takes one outward step and reads `depth_order`. | No learn. | Real numerics. Thin use on a still. | — |
| Frame perception | `perceive_image.py`, `perceive_video.py`, `perceive_language.py`, `perceive_audio.py`, `frame_codec.py` | Image and video project and quantize without `step`, and bin relative error as `rcore_low` / `rcore_mid` / `rcore_high`. Language and audio build a small frame and take a scale address with `step_core=False`. The gate inside `scale_address` still sees the luma/edge label from `embed_frame`. | No learn. No scar update on these paths. | Real quantizer on image and video. Language and audio are addresses only. | Replacing the embed label is the `suite_residual` item left out above. |
| `suite_residual` / `embed_frame` | `src/resileos/ui/suite_residual.py`, `residual_embed.py` | Coarse label from luma, edge, and belt. Docstring still calls it a placeholder. | No. | Stub label. Real only as a stable string. | Leave the label. Image perception already overwrites the returned bin with `rcore_*`. |
| `local_gen` | `src/resileos/ui/local_gen.py` | Tints a random field from three phases. | No learn. Scale address does not step. | Thin scaffold. The cascade note says this is not the codec. | — |
| `fluid_gen` / `media_gen` / `video_gen` | `src/resileos/ui/` | Stills can call a public image URL helper. Video returns unavailable unless `RESILEOS_VIDEO_PROVIDER` is set, and then only if a function or executable exists. No URL is invented. | No residual write. | Wrapper, off for video by default. | Do not treat a configured executable as the core. |
| Chat cycle | `src/resileos/chat/turn_cycle.py` | Hermes-budgeted history, Iris→Metis cycle, Aphrodite, Hades lesson on a verified learn. `zeus_learn` uses reviewers then `zeus_head`. | Learn only through Zeus after review. `turn_residual` still calls `core_step_from_address` on a throwaway core. | Real chat integration. | That throwaway step is outside the visual fix. |
| Mouth | `src/resileos/kin/mouth_policy.py`, `src/resileos/chat/persona_mouth.py` | `should_render_prose` defaults `require_verified=True`. The persona mouth passes that default and `run_cycle=False`, because the turn already cycled. Factual lines require the turn's `verified` flag. A greeting uses the persona pack and skips the cycle. `verified` on that line is false. | No residual write. `remember_verified_learn` saves a Hades lesson and does not call `learn`. | Real template mouth. Not an external chatbot. | `require_verified` was not flipped. A conversational line is not one fixed sentence for every input. |
| `custom_mouth` | `src/resileos/ui/custom_mouth.py` | Speaks from rows. A conflict names the rows and their time windows. A candidate is phrased as an unverified closest match. Optional external model only if one is configured, and not for those explanations. | No learn. | Real structured mouth. | Do not add a chatbot as the mouth. |

`landing/public/_redirects` is not in the tree. This change does not add a `/chat` → `/chat.html` rewrite.

## Temporal residual clip

`src/resileos/studio/clip_codec.py` sits next to the studio codec service. It compresses frames that were already supplied. It does not sample a prompt and it does not call a provider.

Frame 0 is a base packet from the layer-scale studio codec: bipolar factors, one scale per layer, greedy residual layers under the phi rank and depth ceiling. Each later frame is the residual of that frame against the previous packet's chain reconstruction. The temporal residual magnitude is the RMS of that residual. When the RMS is at or under `TEMPORAL_SIGMA` (0.05), the frame is marked `residual-consistent, reuse previous packet` and no delta packet is stored. When the RMS is over the gate, the same stack encodes a delta packet and the frame is marked escalated. The stored sequence is the base packet, the delta list (only the escalated frames), a timeline, and a SHA-256 over the stored packets. Bits per frame are the studio logical bits of those stored packets. The count of reused frames and the count of frames that would need a generative call are reported separately. This inventory does not turn those counts into a savings claim.

`VideoPacket` (`src/resileos/harness/packet.py`) extends `ControlPacket` with `frame_residuals` (packet hashes, one per frame), `temporal_delta` (the largest later-frame RMS), `keyframe_ids`, `provider_stage` (`draft`, `verify`, or `upscale`), and an optional `scene_script_hash`. The script source is not a field.

Phase step and mirror energy come from `residual_frame.py` (`MAGNETIC_PHASE / PHI` times the mean residual gradient, and the mirror-energy check). The clip codec calls those functions. It does not reimplement them. It does not call `ResidualCore.step`, `learn`, or `_scar_update`. `step_core` stays false. `scar_matrix_updated` and `learned` stay false.

`src/resileos/studio/sequence_stage.py` is the verify stage. It decodes the packets and runs `residual_consistency` between consecutive decoded frames, then the sequence hash, Hephaestus, `verify_on_stop`, and Themis when a lesson, an Apollo status, and evidence exist. A passing sequence sets `sequence_verified`. Only that result is written to Hades, and the checkpoint keeps the lesson and the packet hash, not the frame history. Only that result is registered as a candidate.

Upscale is the still contract, with the sigma gate in front of any provider call. It stays off when the residual closes. It is refused on a bad hash, a Hephaestus failure, or a deny risk. An inconclusive residual sends only the failing-frame residual deltas that also clear the sigma gate. A frame marked `residual-consistent, reuse previous packet` is not sent. With no provider the status is `UNAVAILABLE` and `url` is null. No provider is wired. Higgsfield, Seedance, ComfyUI, OpenAI, Kapwing, vidful.ai, aifreevideo.com, and Grok Imagine are not connected. Stable Video Diffusion official weights are non-commercial research only and are not a production path. There is no local SVD slot.

Iris and Hades each append one JSONL record per stage: control id, stage, packet hash, residual energy, consistency score, verify result, budget used, checkpoint id. `RESILEOS_IRIS_JSONL` and `RESILEOS_HADES_JSONL` set the files. `RESILEOS_RESIDUAL_TRACE_CAP_BYTES` caps each file (default 65536). The record has no prompt and no secret. `forge_video` remains a Hermes legion under Hephaestus.

## Video surface

`GET /studio/video` is a plain page. The Streamlit Video tab (`src/resileos/studio/video_page.py`, opened from `ui_studio.py`) is the sibling of the codec panel (`src/resileos/studio/panel.py`). Both call `forge_video` with `clip=True`.

Top to bottom: a prompt and spec box (Hermes ranks the supplied context), Draft / Verify / Upscale, a Hades panel (checkpoint id, lesson, residual hash, a Checkpoint button, and restore fresh), and an output strip. The strip has a timeline of keyframes as residual-decoded stills, a cost meter with the reused-frame count and the count of frames that would need a generative call, decoded previews, a residual badge, packet download, a short control history, and a URL only when an upscale call actually returned one. Upscale stays disabled until Verify returns verified or inconclusive. Draft accepts uploaded frames or a residual packet. A prompt with no frames and no packet is `UNAVAILABLE`. Mouth stays off unless this sequence is verified. A leftover Metis policy from another request does not close a verified clip. Candidates are only the verified sequences. The page links `landing/public/assets/site.css`, `landing/public/assets/chat-ui.css`, and the shared font sheet. Stage buttons use the shared `btn-label` class. Button labels stay plain language.

The page does not copy another product's name or layout. `landing/public/_redirects` is not part of this surface.

## Scene legions

Three Hermes tools sit under the forge, next to `forge_video`. Hephaestus remains the patron and is not a Kin. Each tool is a stub: it writes a scene-description artifact, residual-hashes that file, and asks Hades to checkpoint. No Blender executor is configured. Restore uses `restore_fresh`: the lesson and the residual hash cross the boundary, and the script source does not. The classical core is shown `{"packet_hash": ...}` only.

| Tool | Job | Named for |
|---|---|---|
| `daedalus` | Scene geometry. Stub. | Daedalus, the craftsman who built the labyrinth |
| `helios` | Lighting and materials. Stub. | Helios, the sun |
| `argus` | Camera and animation. Stub. | Argus, the many-eyed watcher |

Existing public names are unchanged. `forge_video` is still the video legion. Dionysus, when present on Hermes, is a different tool and is not one of these three.

## Open work

PR #27 is on `main` at `a640101`. PR #28 is the inventory this section used to follow. The clip codec and the video page are the work that inventory deferred. What is still out is listed in "Left out, and why": `suite_residual`, `LearnedConvCodec`, unwired Lachesis and Harmonia, Nike and Themis on paths that do not have their inputs, and the rheology head. Provider slots stay empty.
