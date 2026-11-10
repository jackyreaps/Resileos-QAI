---
doc: RES-343-demigods
title: Demi-god Skill Layer
status: implemented
depends_on: [RES-334-kin, RES-340-verifier-swarm, RES-201]
---

# Demi-god Skill Layer

Demi-gods are summoned skills under Kin. They are not peers of Iris, Metis, Hermes, Apollo, or Hades, and they are not the residual core.

A summon loads one persona file into the caller's control packet, capped at `GUIDE_BODY_CAP` characters. The matching Python function runs one check and returns a typed result: `verified` / `success`, a reason, and the evidence it actually used. Dismiss removes that guide by exact id (`demigod:<name>`). The persona files are markdown. The decisions are ordinary functions.

## Hierarchy

| Rank | Entity | Role |
|---|---|---|
| Core | Residual core / Zeus | Deterministic authority. Zeus applies a write only after every reviewer approves. |
| Kin | Iris, Metis, Hermes, Apollo, Hades | Standing side-interfaces. |
| Demi-gods | Themis, Momus, Hephaestus, Nike | Summoned skills. One duty, then dismiss. |
| Skills / tools | Everything else | Deferred. Not in the always-visible catalog unless it already lives there. |

A Demi-god cannot call `learn`, take ownership of a residual core, summon another Demi-god, or persist anything beyond the Hades lesson and the residual packet hash. Those two are the only durable values that cross attempts. Guide text stays on the attempt that summoned it. Hades does not store `guide_bodies`.

## Roster

| Demi-god | Serves | Check | Pass condition |
|---|---|---|---|
| Themis | Apollo and the residual core | `themis_check` | `residual_consistency` is consistent, `apollo_success` reports success, and the Hades lesson contains `verified=true`. All three must agree. |
| Momus | Separated-cycle reviewer | `momus_review` | Every explicit requirement holds, and the residual hash is 64 lowercase hex characters when one is in play. |
| Hephaestus | Residual core, for structure | `hephaestus_check` | `residual_consistency` passes, scars are empty, `budget_and_stuck_guard` passes, and declared loads sit under `hopfield_cap` / `check_capacity`. |
| Nike | Apollo | `nike_check` | Every explicit criterion holds, backed by Apollo success or residual consistency. |

Missing evidence fails. Themis fails when the packet, the Apollo `status`, the lesson's verified signal, or a real evidence entry is absent. Momus cannot approve when it has no requirement checks to run; a bare residual hash is not approval. Nike fails when the lesson and the task brief contain no `criterion:`, `success:`, or `must:` line (and no `criteria` list). Hephaestus fails a missing budget, an unresolved scar, a guard failure, or a load at or over `hopfield_cap`.

Momus is blind in code. Before it compares, it drops `history`, `control_history`, `author_notes`, `author_note`, `evidence_gist`, and `reasoning`. Those values are not copied into the result. A requirement that is true only inside stripped text is a defect.

## Summon and dismiss

`demigod_summon` and `demigod_dismiss` write the caller's `ControlPacket`, or a dict the caller keeps. `ControlPacket.to_dict()` shares `guides_loaded` and `guide_bodies`, and both operations edit those objects in place, so a dict taken from `to_dict()` still updates the packet.

Guide files are read with `importlib.resources` from `resileos.kin.demigods.guides`. Names must match `^[a-z][a-z0-9_]{0,63}$`. The router then accepts only a direct `*.md` entry in that directory. `../x`, an unknown name, and an empty roster raise `DemigodError`. They do not inject a guide.

`guide_load` is the single place a body is truncated. Summon passes the file text and `GUIDE_BODY_CAP`.

## Maker and blind verifier

`maker_blind_verifier_cycle` lives in `resileos.harness.separated`.

1. The maker runs with a full control packet.
2. If `control.verified` is true and a Hades store was passed, the cycle saves a checkpoint and keeps `ckpt.lesson`. If `control.verified` is false, it does not save and the lesson stays unset.
3. Momus is summoned onto a separate review packet. The review calls `momus_review` with the artefact, the spec (or the task text when no spec was passed), and `residual_packet.packet_hash`.
4. The verdict goes through `zeus_head`. `learn_fn` runs only when that verdict approves.
5. Momus is dismissed. The guide id is gone from the review packet.

## Tool surface

`DEMIGOD_TOOLS` holds `demigod_search`, `demigod_summon`, `demigod_dismiss`, and `list_demigods`. Those names are not in `ALWAYS_VISIBLE_TOOLS`, not in `harness_tool_schemas()`, and not in the answer-tool schemas. `GET /api/v1/tools` stays the always-visible catalog. `GET /api/v1/tools?q=` calls `search_tool_surface`. A blank query returns no rows.

## Honest limits

These are deterministic checks plus persona text. No language model is wired up. Summoning Themis does not generate a judgment; `themis_check` compares three existing signals. Momus does not read prose and invent defects; it evaluates explicit requirements (`equals`, `contains`, `present`, or `MUST:` / `criterion:` lines) and the shape of a residual hash. Nike does not infer a victory condition from a Hades sentence such as `verified=true`; that sentence is Themis's signal, and Nike ignores it unless it is also an explicit criterion. Hephaestus does not invent a fact count: a load is checked only when `n_facts` or `hopfield_count` is declared, against `hopfield_cap` via `check_capacity`. An undeclared load is reported as undeclared. Evidence length is always compared with `EVIDENCE_CAP` (the cap `evidence_attach` already keeps).

`residual_consistency` treats a packet with no scars and no broken `residual_core` hash as consistent. Themis adds the evidence requirement on top of that, so an empty packet does not certify. Nike's `residual:consistent` criterion uses the primitive as it is.

Nothing in this layer writes the residual core, calls `learn`, or keeps a Demi-god on the packet after dismiss.
