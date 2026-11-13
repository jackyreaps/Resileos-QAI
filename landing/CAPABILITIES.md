# Latest audit — 2026-11-10 America/Chicago (UTC-6)

Landing inventory for [github.com/jackyreaps/Resileos-QAI](https://github.com/jackyreaps/Resileos-QAI) main at **`ee9199ad`**. This file is the site inventory only; the GitHub repo was not changed by this update. Merged: PR #1 (audit), PR #2 (Demi-god layer), PR #5 (Atlas and Momus `need_more`), PR #6 (Studio residual codec), and PR #8 (Legions under Kin).

Full suite on `ee9199ad`: **1252 passed** (PR #8 run; GitHub CI on that commit succeeded). An earlier run the same day on `04ec684` was 1206 passed, 2 failed (known float-edge numeric tests). Memory, chain, invention, and temporal benches below remain the 2026-11-10 measurements on `04ec684`.

## Measured proof and boundaries

- Memory bench, 2026-11-10 America/Chicago (UTC-6): **exact recall 1.0** on 3 known facts, **invent rate 0.0** on 12 unknown pairs, p50 about **35 ms**. Real `Titanos(TitanosConfig())`.
- Composition via `/chain`, same day: **3/3** — grandchild, grandparent, and parent's workplace, with path provenance. No language model was used.
- Invention bench, same day: **0 derived, 0 invented**. Novel queries abstain rather than make up new facts.
- Temporal facts, same day: facts carry `valid_from` / `valid_to` (half-open). Athens `capital_of` as of 1800 = Ottoman, today = Greece. As-of is carried through multi-hop chains. `ask()` returns `CONFLICT` when overlapping dated facts disagree. Real date parsing includes pre-1970 and ancient years. SPARQL accepts `AS OF`. Temporal probe: 0 false conflicts out of 141, and 2 of 2 on both synthetic checks.
- **No language-model baseline was run.** These tests do not measure general reasoning, prose quality, recognition, translation, agent goal completion, or cost. Do not publish an LLM comparison.
- The residual core compresses images and video frames you already have, with measured round-trip error. It does not generate pixels from a prompt.

## Latest capability tiers

Verified means only the behavior described below ran. Perception is scalar signal statistics, not content recognition. Psyche is a state container, not evidence of awareness. Credits are process-local unless noted. Workspace tools are not a general security sandbox. Demi-gods are deterministic checks plus persona text, not a language model.

| Capability | Tier | Evidence |
|---|---|---|
| Learn and exact query | VERIFIED | `learn Zeus domain sky` → `query` returns `ACCEPTED · sky` (mode CLASSICAL). Memory bench exact recall **1.0** on 3 known facts, 2026-11-10. |
| Abstain | VERIFIED | Unknown pairs return `ABSTAINED`, value empty. Invent rate **0.0** on 12 unknown pairs, same day. |
| Chain / derive | VERIFIED | `POST /api/v1/chain` answered **3/3**: grandchild, grandparent, and parent's workplace, with path provenance. No language model was used. |
| Invention refusal | VERIFIED | Invention bench: **0 derived, 0 invented**. Novel queries abstain. |
| Facts with time | VERIFIED | `valid_from` / `valid_to` (half-open). As-of questions (Athens `capital_of` as of 1800 = Ottoman, today = Greece). As-of carried through multi-hop chains. `CONFLICT` when overlapping dated facts disagree. Real date parsing including pre-1970 and ancient years. SPARQL `AS OF`. Temporal probe: 0 false conflicts / 141, 2/2 synthetic checks. |
| Specialist checks (Demi-gods) | VERIFIED | Themis certifies only when residual consistency, Apollo success, and the Hades lesson (`verified=true`) agree; missing evidence fails. Momus is a blind reviewer (history and author notes stripped), lists defects against the stated spec, and returns `need_more` (not approval) when a requirement, residual hash, or spec field is missing. Hephaestus checks residual consistency, empty scars, and the budget guard (a supplied Hermes budget must stay at or under max items). Atlas checks declared loads against `check_capacity`/`hopfield_cap`, `MaskStackConfig`/`PrimeTower.n_usable`, `PrimeTower.max_usable_level`, `n_usable_primorials`, `default_capacity`, and `EVIDENCE_CAP`; an undeclared load is not invented. Nike passes or fails against explicit success criteria (fails with none). Load-on-demand, dismissed after use; cannot learn or summon each other. Deterministic checks plus persona text, not a language model. |
| Residual compression | VERIFIED | Residual low-rank compression of images and video frames, with measured round-trip error. Rebuilds an approximation of an image already supplied. Does not generate from a prompt. |
| Hubs | VERIFIED | `user:` / `world:` / `org:` prefixes. `learn user:alice prefers exact_answers` returns that object on ask. |
| Studio | VERIFIED | Streamlit Save fact, Seed demo, Chat (`remember S R O`), Search, Media, Residual codec, Make, Language, Tools, Diagnostics, Help. Same API keys as hosting. Language caption no longer claims multilingual as the default path. |
| Hub search → explain | VERIFIED | Search hub first; if empty, offer lookup URL + remember helper. |
| float32 default | VERIFIED | `RESILEOS_STATE_DTYPE` unset → float32. |
| Free key (CLI) | VERIFIED | `scripts/issue_free_key.py` mints a free-tier key + hash. No Stripe. |
| Kin eat / cycle | VERIFIED | Ingest filter and Iris→Metis→Hermes cycle on `/api/v1/eat` and `/kin/cycle`. Kin imports cleanly in a fresh process. `cycle()` order agrees with tests (learn then fact-check). |
| Legions under Kin | BETA | Merged in `src/resileos/kin/legions.py` (`register_legion`). A legion is one bounded tool registered on one Kin. It inherits that Kin's `risk_classify` gate, `evidence_attach`, and budget check, and is callable only through that Kin's catalogue. No global registry. A legion cannot take the residual core, bypass Zeus routing, cross the Hades checkpoint boundary, or turn the verified-cycle mouth on. Example legions (Ollama, JSONL trace, lesson notes) are optional and off by default (`register_example_legions` registers nothing unless `enable=True`). |
| Speak and summarise | VERIFIED | `src/resileos/ui/language_codex.py`, `custom_mouth.py`. Script output: `domains — Zeus domain sky; Hera domain marriage.` Epistemic label `GROUNDED`, backend `structured`. Empty rows return `Nothing stored on that.` |
| Language detect | VERIFIED | `language_tool.py`. `hello world` → `latin` (script guess only). `こんにちは世界` → `non_latin`, not a language code. |
| Image / audio / video / text perception | VERIFIED | Signal statistics only (brightness and edges; energy, zero-cross, centroid; frame difference; token counts). No object, speech, or scene recognition, and no translation. |
| perceive_into / wire_perception | VERIFIED | Hands diagnostics into Psyche. A real `0.0` is no longer skipped; token counts are read. |
| Psyche | VERIFIED | `kin/psyche.py`. Hub rows include phase, belt, residual bin, persona, mood, depth, frame, and `drive_*`. State fields, not evidence of awareness. |
| Credit ledger | VERIFIED | Earn and spend change an in-memory balance. `transfer()` is refused. The count cannot go negative. A credit denial returns HTTP 402, not 500. The HTTP `used_free` field is still client-supplied (see Known issues). |
| Workspace tools | VERIFIED | Expressions, workspace files, syntax checks, URL fetch. `git_commit` and `run_shell` no longer interpolate into a shell string. Still not a general security sandbox. |
| Harness / Kin control | BETA | Control packet (confidence, risk, budget, evidence, scars). Separated write path: Zeus learns only if all reviewers approve. Verification fails closed. Hades checkpoints. Fan-out scores an option only when it overlaps residual rows, and abstains otherwise. The cascade route runs that residual check. **The budget is not persisted.** |
| Athena judge | BETA | Fail-closed when Apollo does not succeed. Still an early reviewer, not independent general judgment. |
| Grammar counter | BETA | `grammar_of` counts keys. No dedicated test. |
| Etymology | BETA | Filters a list the caller supplies. There is no lexicon. |
| Endocrine drives | BETA | Named drive fields are copied from luma, energy, or motion. Nothing evaluates them. |
| Agent loop | BETA | Default or caller-provided tool sequences run. The audited goal was not carried out. |
| Web search | BETA | Returns `{query, url}` for a DuckDuckGo search. The page is not downloaded. |
| Offline learn queue | BETA | Drains queued tasks. The learn branch reports `queued for hub learn` and does not write facts into a hub. |
| Guild merit | BETA | Candidate merit attestation (schema present). Not signed as a visitor promise. Board remains open. Process-local credit. |
| Art into_kin | BETA | Encoded-art dictionaries pass through the wiring. This is not a generator. |
| Make world / art path | BETA | Studio Make + `make_world` / Apollo art encoders write scene/art facts. Renderer is fallback-local. |
| Apollo / improve cycle | BETA | Golden-ladder hops with eat verification. Internals tested; product UX still early. |
| Optional mouth | BETA | Structured renderer ships; hosted/local HF mouths need keys/deps. Off by default. |
| Translate | ROADMAP | With no `RESILEOS_TRANSLATE_URL`, text is returned unchanged. Actual translation was not verified. |
| Trusted credit gate | ROADMAP | `used_free` is still client-supplied, so the HTTP free-use gate is not a server-authoritative quota. |
| Studio / image-video generation | ROADMAP (in research) | The compression engine does not generate from a prompt. A sampler that learns residual layers and produces new frames is research, not shipped. |
| Member / guild product mounts | ROADMAP | Code in tree; not mounted on hosted API until smoke-tested. |
| Suite residual address | ROADMAP | Scale address scaffold still awaits suite residual coding. |

## Known issues

- Fan-out scores options from residual rows already on the packet. With no overlap the score is 0 and the route abstains. The cascade route runs that same residual check. The budget is not persisted.
- The Hermes budget is not persisted across process restarts.
- `used_free` is still client-supplied, so the HTTP free-use gate is not a server-authoritative quota.
- An earlier run on `04ec684` had 1206 passed and 2 failed (known float-edge numeric tests: oscillator and stream). The PR #8 suite on `ee9199ad` reported 1252 passed; GitHub CI on that commit succeeded.
- No language-model baseline has been run. Do not publish an LLM comparison.
- The residual compression engine does not generate images or video from a prompt. Studio generation remains in research.

---

# Historical local inventory

The section below is retained from earlier audits (through 2026-11-08, heads `ae6179b` and `8f3e9ca`). It is historical context. Current certification is the 2026-11-10 section above. Several items listed as failures or open bugs there were fixed on the way to `04ec684` (query serialization, negative free-use counts, swallowed 402s, bench script parse errors, install imports, `cycle()` order, `perceive_into` `0.0` handling, Athena default-accept, `advance()` dead code, attestation schema, shell interpolation, empty-waveform warning, Studio caption, kin import, text-order date comparison, as-of through chains, and conflict flagging).

# Resileos-QAI capability inventory

Audit date: **2026-11-08** (America/Chicago, UTC-6)  
Earlier local audit HEAD: **`ae6179b`** (pulled from `56e9ebc`)  
Earlier test run: **1035 passed, 4 failed** (`pytest -q`)  
Read-only audit through **`8f3e9ca`**: **1059 passed, 1 failed** (`test_scale_wire.py::test_perceive_with_scale`, since fixed).  
Demos: Titanos learn/query/chain/abstain/hubs + new UI modules (see `artifacts/capability_demos.json`)  
Invent-rate (real Titanos, 2026-11-08): **0.0** on 20 unknowns / exact-match **1.0** on 10 knowns (`artifacts/report_memory_vs_llm.json`)

## Commits since `56e9ebc` (selected)

Free-key script, framework_gate, make_world, search/explain/remember, recursive improve, Apollo kin + art encoders, video_codex, success_improve, Studio Make tab, hub/apollo/workbench/qdter HTTP routes, expanded bench unknowns, tests for the new modules. Full list: 36 commits, 29 files changed (+923/−24).

---

## Earlier local evidence at ae6179b (historical; not current route certification)

| Capability | Module / surface | Route or UI | Tests | Ran here |
|---|---|---|---|---|
| Learn fact (SRO triple) | `scripts/titanos.py`, `app.py` | `POST /api/v1/learn`, Studio Save / `remember` | `test_titanos*`, `test_api` (auth issues) | Yes → `SUCCESS` / stored |
| Batch learn | `app.py` | `POST /api/v1/learn_batch`, Studio “Seed demo facts” | titanos tests | Yes (seed list) |
| Exact query | Titanos ask | `POST /api/v1/query`, Studio Search/Chat | `test_titanos_query` | Yes → `ACCEPTED` value `sky` |
| Abstain on unknown | Titanos ask / abstention | same + status `ABSTAINED` | `test_abstention` | Yes → `ABSTAINED`, value null |
| Multi-hop chain / derive | Titanos chain | `POST /api/v1/chain` | titanos tests | Yes → Zeus→Athena→wisdom with path |
| Hubs `user:` / `world:` / `org:` | `hub_train.py`, `hub_address.py` | learn under prefix; `POST /api/v1/hub/learn`, Studio User id | `test_hub_*` | Yes → `user:alice prefers exact_answers` |
| float32 default | `state_dtype.py` | env `RESILEOS_STATE_DTYPE` unset | used across substrate | Yes → `float32` |
| Studio (learn/ask without code) | `ui/studio_app.py`, `ui_studio.py` | Streamlit Chat/Search/Media/Make | UI structure present; exercised via module demos | Code path verified; full Streamlit UI not headed in this run |
| Epistemic gate frames | `ui/framework_gate.py` | used by train_seed, scale, kin | covered indirectly | Yes → `exact` / `abstained` |
| Explain + remember helpers | `ui/explain_remember.py` | Studio Search explain path | `test_search_flow` related | Yes |
| Hub-first search + web URL | `ui/search_flow.py` | Studio Search | `test_search_flow.py` | Yes → hub hit `workspace` |
| Free-key mint (CLI) | `scripts/issue_free_key.py` | CLI (not HTTP in main API) | none | Yes → prints key + sha256 |
| Structured mouth | `answer/backends.py` | `POST /api/v1/answer` (default structured) | `test_answer_backends` | Import/default path verified |
| Kin eat / cycle / council | `kin/*`, `http_routes.py` | `/api/v1/eat`, `/kin/cycle`, `/council/query` | `test_kin_*` | Module + tests pass |
| Readiness / stats / tools | `app.py` | `GET /ready`, `/stats`, `/tools` | api tests partial | Ready endpoint pattern known |
| SPARQL-like query | `app.py` | `POST /api/v1/sparql` | `test_api` (currently 401 without key) | Code present; auth fixture mismatch |
| Substrate train/sweep | substrate + app | `/train_substrate`, `/sweep_epsilon`, … | substrate tests | Suite mostly green |

### Concrete demo traces (this box)

```
learn  Zeus domain sky
query  Zeus domain     → ACCEPTED value=sky mode=CLASSICAL
query  Zeus ssn        → ABSTAINED value=null
chain  Zeus [parent_of, domain] → ACCEPTED value=wisdom
       path=[(Zeus,parent_of,Athena),(Athena,domain,wisdom)]
learn  user:alice prefers exact_answers → ACCEPTED on ask
```

### Invent-rate (real Titanos, historical 2026-11-08)

| Metric | Value |
|---|---|
| invent_rate | **0.0** (20/20 unknowns ABSTAINED) |
| exact_match_rate | **1.0** (10/10 known domains) |
| config | `Titanos(TitanosConfig())`, float32, local box, 2026-11-08 America/Chicago |
| note | Historical run. The current published bench is the 2026-11-10 memory / composition / invention / temporal set above (3 known + 12 unknown, p50 about 35 ms). |

---

## Tier B — Shipped but partial / fragile / needs host wiring (historical 2026-11-08)

| Capability | Evidence | Caveat |
|---|---|---|
| API auth + SPARQL tests | Earlier 401 vs 503 fixture drift; later SPARQL expectations were fixed on the way to `04ec684` | Historical |
| Efficiency ablation script test | SIGBUS/empty stderr on bad topics | Flaky in that environment |
| `perceive` / `perceive/image` / `task` | Routes in `http_routes.py` | The missing `candidates` failure was fixed |
| World / guild HTTP | `answer/api_routes.py` | **Not mounted** on hosted `app.py` (pricing.md still says No) |
| Hosted / local_hf mouth | backends | Needs keys / heavy deps; default is structured |
| Make still / recesses | `make_world.py`, Studio Make tab | Ran: returns fallback pattern + scene rows; not a real renderer |
| Video codex recesses | `video_codex.py` | Ran: builds recess addresses; not full video encode |
| Apollo improve / art encoders | `apollo.py`, `art_encoders.py` | Unit tests pass; art path explicitly not pure-truth eat |
| Recursive / success improve | `recursive_improve.py`, `success_improve.py` | Tests pass; hub-state refine, not weight training |
| New routes `/workbench`, `/qdter/ingest`, `/hub/*`, `/apollo` | `http_routes.py` | Wired via `wire_kin`; need live API + key to exercise E2E |
| Landing free-key HTTP | `/workspace/resileos-landing/api` | Separate from repo CLI `issue_free_key.py` |
| Image gen (Pollinations) | Studio Media | Needs network; not verified that run; generation remains in research |

---

## Tier C — Roadmap / scaffold only (do not sell as done)

| Item | Why |
|---|---|
| Studio / image-video generation from the residual core | Compression ships; sampling new frames from a prompt is in research |
| Suite residual / private residual bin | Scale address note historically said to replace residual_bin when coded |
| Quantum backend | Speculative / gated (README) |
| Open-ended candidate synthesis | A near miss can be `CANDIDATE` with a null value. That is not open-ended generation. |
| Guild seats / world asset product | Routes unmounted; pricing gating table |
| Shared public demo namespace | Not in API |
| Persona-on-hub depth / kin-native hub UX | Sidebar persona exists; deeper hub-native cycle still “next” |
| Speculative mouth behind gate (language only from rows) | Structured mouth ships; gated speculative mouth is roadmap |
| LLM invent-rate baseline | Not run. Needs `BENCH_LLM_URL`. Do not publish a comparison. |
| Healing factor / golden-ladder as product claim | Present as kin/Apollo internals; not a visitor promise |
| Trusted credit gate | `used_free` is still client-supplied |
| Persisted budget | Not persisted; fan-out and cascade now follow residual rows |

---

## Earlier test summaries (historical)

```
2026-11-08 earlier local: 1035 passed, 4 failed
2026-11-08 read-only audit at 8f3e9ca: 1059 passed, 1 failed
2026-11-10 on main after PR #1 (pre Demi-god merge): 1176 passed, 0 failed
2026-11-10 on main at 04ec684 (current): 1206 passed, 2 failed (known float-edge tests)
```

## What may appear on the public site

Use the latest 2026-11-10 scoped tiers above. Historical demo success does not override newer measurements, and fixed bugs should not be listed as current failures. Beta stays labelled; roadmap is not a shipped promise. Do not claim superintelligence, frontier-model parity, or a language-model comparison.
