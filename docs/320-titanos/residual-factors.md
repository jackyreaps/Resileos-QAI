# Residual factors

Content-free residual factors can train greater hubs without exposing
source content. This is the default training path. Sharing richer
material still uses [cascade promotion](tier-promotion.md) and still
requires opt-in.

## Two levels

1. Default. A verified residual factor with no content, energy at or
   above the 1/64 debt quantum, and a factor count at or under the
   waist of 36, may train `org:` (local) and `world:` (global) without
   opt-in. A contributor can opt out per record (`opt_out=True`) or by
   listing an ident in `opt_out_ids` on the aggregate. Nothing is
   emitted until at least `MIN_CONTRIBUTORS` (3) verified, not-opted-out
   contributions remain, so one person is not visible as a cohort.
2. Open. Verified richer material still moves one step outward only
   through `resileos.persona.promote`, and only with opt-in.

Writes still go only through Eat, with reviewer approval. This path
never calls `Titanos.learn` directly.

## What a factor holds

A factor is a structural signature, not a clip, sentence, or pixel
buffer:

- residual bin, Human Belt (5), chroma axes, orientation scale level
- factor count (clipped at the waist)
- quantized error and scar energy
- residual improvement against a previous energy
- φ weight at the orientation scale
- a fingerprint over those fields

Content keys (`text`, `frames`, `pixels`, `obj`, and similar) are not
accepted. An ident is kept only so opt-out can match, and is never
copied into the aggregate.

Values are quantized to 1/64. Aggregates are JSON compact enough to
fit the Eat object length.

## Dream consolidation

`morpheus.dream_factor_candidates` recombines aggregates into
unverified candidates. The dream stage never calls learn, never
updates a scar matrix, and never writes Titanos. A later verification
gate (`offer_factor_candidate`) returns an Eat envelope and does not
write. Only a verified candidate is offered to Eat, and only a
verified candidate is also copied into an [upgrade
proposal](upgrade-proposals.md).

Code: `src/resileos/persona/residual_factors.py`,
`src/resileos/kin/demigods/morpheus.py`.
