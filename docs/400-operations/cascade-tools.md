# Cascade tools in the composer and Studio

`src/resileos/chat/cascade_tools.py` builds user-facing tools from math the
suite already has. None of them needs an outside provider.

| Tool | Math it uses | Where it shows |
|---|---|---|
| Upload address + code | `pin_address("individual")` (belt 5, frame 5, waist 36, keep floor 1/64), `suite_residual`, `chroma_code` / `pack_code` (23-byte belt code) | Every perceived upload in `/assist` (`assist.attachments[].address`, `.code`) |
| Source ranking | Hermes search/crawl envelopes, `cascade_address(5, frame, qN)` with frame from provider rank on 3/5/9/12, ordered by score = relevance · φ^-(frame-3) (the frame's φ address relative to frame 3 = 1; an address for ordering, never a gain and never a halving step), `keep_packet` on the result's energy (its relevance) only, so a frame-12 result with energy ≥ 1/64 is kept, `clip_factors` (≤ 36) | `/assist` search step; sources carry `address` and `score`; the top 2 are crawled with the guarded fetcher |
| Picture variations | Belt coordinates (black, white, red, blue, yellow) + `expand_variations` (belt rotation, RBY permutation, φ hue steps), picked by the golden-ratio sequence; the photo's own brightness is kept | Chat ("make a variation of this"), Studio picture from a photo (`POST /api/v1/studio/variations`) |
| Clip from one picture | φ hue steps over time + the `MAGNETIC_PHASE / PHI` motion step as a pan; `clip_check_metrics` recorded (not gating) | Chat ("make a clip from this"), Studio clip from one photo (`POST /api/v1/studio/clip-from-picture`) |
| Clip variation | One expanded palette on every frame of an uploaded clip | Chat, `POST /api/v1/studio/variations` with `frames` |
| Use factors | `turn_factor` → `residual_factors.factorize` (one record per **checked** turn, built only from which gate passed and how many steps finished: no attachment, pasted text, or perception value), `aggregate_factors` (≥ 3 contributors, local hub), `offer_to_eat` (envelope stays pending for Eat), Morpheus `dream_factor_candidates` (unverified) | Recorded per `/assist` turn to `RESILEOS_FACTORS_PATH` (default `data/use_factors.jsonl`); admins read `GET /api/v1/factors/hub` in Admin → Diagnostics |

Rules kept:

- Nothing here calls `learn`, writes Titanos, or writes a scar. The hub
  aggregate is an Eat envelope with `eat: "pending"`; Eat and reviewers
  stay the only writers.
- Factors count only when the turn passed a gate (Lean `CHECKED`, or a
  reply marked verified), and they never include attachment or pasted
  content. Attachments and Files don't feed the factor at all.
  People can turn sharing off in chat (Options → Share anonymous patterns).
- A picture or clip from a text description alone still needs a
  generator. Without one it stays `UNAVAILABLE`.
