# Studio app (`/studio`)

Studio is its own full-screen app with its own section rail. It shares sign-in, Files (through chat handoff and uploads), and the stream layer with the rest of the site. It has three equal pillars on one asset board:

| Pillar | Where | What it does |
|---|---|---|
| World building | World, Characters, Scenes, Game rules | Covers:<br>• lore, places, and factions<br>• a timeline whose lines are quintuples (subject, relation, object, `valid_from`, `valid_to`), with an overlap and order check<br>• characters on the persona store's individual tier (pin `5/5/…`, no promotion)<br>• scenes with storyboards<br>• an open game system (stats, entities, rules, invariants) with a 12-round rule check and an optional Lean proof of the starting values |
| General video | Clips | Covers:<br>• a clip timeline and player<br>• a clip from one picture (φ hue steps plus the φ motion step)<br>• several pictures used as keyframes with blended in-betweens<br>• recoloring a clip<br>• turning a storyboard into a clip<br>• a provider slot for text to video, which shows **UNAVAILABLE** when `RESILEOS_VIDEO_PROVIDER` is not set and is never faked |
| Advanced image creation | Pictures, All assets | Covers:<br>• uploads to the board<br>• color-code variations at an orientation scale (close up, near, far, farthest)<br>• edits in layers: brightness and contrast, recolor, scale color, simplify (level), mirror, crop, and laying another picture over it<br>• batches across picked pictures<br>• compare and pick<br>• a levels view |

Labels are plain. Codes, addresses, and edit stacks appear only under **Details**. Anything Studio made carries the tag "Made · not checked". Dreams carry "Dream · not checked".

## One leveled core (`resileos.studio.level_core`)

Every tool runs on one upper layer that mirrors the cascade:

- **Levels are cascade frames at their φ address.** `cascade_address.frame_control` / `phi_address` define them. They are not a halving pyramid: frame *f* is an *f* × *f* grid, so the levels are 3×3, 5×5, 9×9, and 12×12.
- **Scaling and decompression are leveling.**
  - `level_down` splits a picture into a base plus one band per frame and a detail rest. Each band carries its `frame_control`, energy, and whether it clears the 1/64 floor.
  - `level_up` / `decode` put the bands back up to a frame. With detail included, the result is lossless.
  - The 5-frame is the pentagram orientation, with no waist span.
- **Video** levels in time: frame *f* keeps *f* keyframes (`keyframes`, `clip_at`), and the in-betweens are blended.
- **Worlds** level in depth: 3 is the world, 5 is places and factions, 9 is scenes, and 12 is assets (`world_at`).
- **Overlays** control recursive sub-instances:
  - Layers composite in strength order: Porter–Duff "over" for pixels (`compose`), and the stronger opinion wins for structured data (`merge`).
  - A sub-instance sits one frame out from its parent, at that frame's φ address. The address places it and never dims it.
  - `instances` stops only at 36 copies in the sector, past the 12-frame, or when a sub-instance's own residual energy is under 1/64. Each copy carries its frame's span as block-size metadata.

There is one core and no separate engines per pillar: `studio_ops` calls the same functions for pictures, clips, and worlds.

## Storage and rules

- Projects are stored per account under `RESILEOS_STUDIO_DIR/<owner hash>/<id>.json`, on the individual tier. Trial visitors can't keep projects. The limit is 50 projects of up to 4 MB each.
- Picture data in a project only ever comes from the server's own operations. A client save can rename, annotate, reorder, or remove assets, but it can't swap their pixels.
- Studio never calls learn, never touches scars, and never writes Titanos (the test suite checks this from the AST).
- **Promotion goes only through Eat, and only with opt-in.** "Offer to shared knowledge" is off by default. When it is on, Studio previews what Eat would do with the chosen timeline lines and writes nothing. An admin saves them from Admin → Knowledge → Add facts, where Eat and the reviewers decide.
- Chat's "make from this" opens `/studio?from=chat`. A signed-in user gets a new project with the attachment on its board.

## API (`/api/v1/studio-projects`, public through the Pages session proxy)

`GET` and `POST` on the collection. `GET`, `PUT`, and `DELETE` on `/{id}`. `POST /{id}/op/{name}` runs an operation, and `POST /{id}/stream/{name}` runs it as typed SSE parts (`start`, `cycle`, `step`, `address`, `abstain`, `final`, `done`). Those parts are resumable and cancellable through the chat stream routes.

The operation names are `add_asset`, `edit`, `variations`, `clip`, `recolor_clip`, `storyboard_clip`, `text_to_video`, `build_world`, `pick`, `levels`, `check`, `world_level`, `lean`, `dream`, and `promote`.

## Research recommendations used (`/workspace/notes/studio-research.md`)

- **#1 Leveled core:** used. `decode(level)` is shared by image, video, and world, with the ε band floor and the waist cap. Frames are φ-addressed grids, replacing the report's "standard dyadic pyramid" caveat.
- **#3 Overlay with inheritance:** used, as a small subset: layers, strength order, "over", and recursive instances bounded only by the waist of 36, frame 12, and the energy floor.
- **#5 Phase-based video:** used, through Muse. In-betweens are phase-based on the cascade bands, and each level gets a Kuramoto coherence score (`clip_metrics.phase_band_coherence`). It uses a whole-picture phase unwrap instead of a steerable pyramid.
- **#8 Temporal lore consistency:** partly used. Quintuple bounds with an Allen-style overlap and order check. Datalog rules are not done yet.
- **Runners-up:** structured game rules with Lean invariants (§10), and the native edit operations (§11): tone, crop, mirror, and over.
- **#7 Leveled WFC:** partly used, through Muse. WFC runs at frame 3 (regions) and frame 9 (scene tiles). Frame 12 detail tiles and the Penrose pentagrid wait on two questions (see Muse below).
- **Not used yet:** #2 VSA layer, #4 resonator cleanup, #6 MAP-Elites, #9 persistence metrics, #10 color upgrades.

## Frame math (the user's rule)

- φ^-(f-3) is an **address** relative to frame 3, where it equals 1. `frame_weight` is used only to rank and to order levels.
- Color and detail are at full strength at every frame. Palette, color, and Studio variation strength are never multiplied by the address. Outer frames place content; they don't dim it.
- ε = 1/64 is a floor on residual energy only, never on the address. A packet, search result, wave result, band, or sub-instance at any frame is dropped only when its own energy is under ε.
- The waist of 36 is the only total limit.
- The span 36/f is the block size at that frame (36/3 = 12, 36/9 = 4, 36/12 = 3), a structural block division. It is a label, not a per-parent child cap or fan-out. Frame 5 has no span: it is orientation only.
- Nested copies run through frame 12. `instances` stops only at 36 copies in the sector, past frame 12, or when a copy's residual energy is under 1/64.

## Muse: native video and world building

Muse is a legion under Apollo, not a Kin (`kin/studio_tools.py`: `muse`, `run_muse`). It is the generative leaf of the harness.

- **Interface.** A ControlPacket and a brief (`clip`, `environment`, or `text_video`) go in. Evidence, a confidence, and a cost (`seconds`, `memory_mb`) come out.
- **Evidence, never facts.** Muse never verifies, even if a caller passes an Apollo success. It never calls learn, never touches scars, and never writes Titanos. Eat stays the only writer.
- **Packet fields.** The optional ControlPacket fields `generative_source`, `generative_cost`, and `generative_evidence_id` record what made the evidence and what it cost.
- **Budget.** The budget guard counts time and memory. A run that overspends returns `OVER_BUDGET` and its evidence is dropped.
- **Hades.** It keeps only a one-line lesson.
- **No outside models.** Muse is not on the confidence cascade: Studio calls it, or a caller names it explicitly.

### Engines (on the leveled core)

- **Clips** (`level_core.phase_inbetween`, `phase_clip`):
  - Keyframes are leveled into the 3/5/9/12 bands plus detail.
  - Each band is mixed in the Fourier domain: magnitudes are interpolated, and phases move along the dominant motion found by phase correlation. A moving shape therefore travels instead of cross-fading.
  - Bands mix at full strength.
  - The time steps are the ones Studio already used: held keyframes, and in-betweens at j/per.
  - Each clip is checked with `clip_check_metrics` and `phase_band_coherence`. Confidence is the mean per-level R.
- **Worlds** (`level_core.environment`, op `build_world`):
  - Frame 3: a 3 × 3 region layout by WFC (span 12 on the 36 lattice).
  - Frame 5: places and factions are put into land regions. This is the orientation frame, so it has no span and no tiles.
  - Frame 9: a 9 × 9 scene-tile layout by WFC (span 4). Each tile is limited to what its region can hold, so each region's 3 × 3 tiles nest exactly.
  - The map is the 36 × 36 waist lattice, with colors at full strength.
  - The scene graph is the overlay tree world (3) → places (5) → scenes (9) → shot assets (12).
  - Game rules are played and checked, and a Lean source is produced when the game has whole-number stats.
  - Confidence is the share of checks passed.
- **From a description:**
  - With a scene set in a place of the world, Muse makes a slow pan over that world's map, starting at the place. It uses the magnetic-phase/φ motion step and 12 frames, as single-picture clips already do. The page says plainly that the words were not turned into pictures.
  - Words alone, or a scene with no place, stay `UNAVAILABLE` with `url: null`. The external provider slot is unchanged, and it is `UNAVAILABLE` when no provider is set up.

### Not built yet (questions for the user)

1. **Frame-12 detail tiles.** A frame-12 block is 3 units and a frame-9 block is 4, so detail tiles straddle scene tiles. Should a detail tile take its constraints from the scene tile under its center, from every scene tile it overlaps, or nest directly in the frame-3 region (12 is a multiple of 3, giving 4 × 4 per region) and skip 9?
2. **Penrose pentagrid.** Frame 5 is orientation only. Should the pentagrid give each frame-5 place one of its five orientations? If so, which line spacing on the 36 lattice? Or should it bias WFC tile weights, and at which frame? Its φ inflation does not line up with the 3 → 9 → 12 lattice ratios (3 and 4/3), so the level mapping is a choice.
