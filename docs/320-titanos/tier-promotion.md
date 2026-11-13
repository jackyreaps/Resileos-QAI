# Cascade promotion

`src/resileos/persona/promote.py` returns the next-scale subject
for a residual fact. It does not re-verify (the live CascadeRouter
sets `verified`), it does not write, and it does not call Eat, learn,
or the scar matrix. A caller that wants the fact stored hands the
returned subject to the existing Eat / learn path. Studio, visual, and
persona paths still do not call learn.

No scar update beyond the learn at the scale that accepted it.

## Opt-in

Richer material still moves up a tier only by explicit opt-in.
`promote` requires both `verified=True` and `opt_in=True` (or a
non-empty consent token). Unverified facts, and verified facts
without opt-in, are refused and stay at their current scale. There
is no automatic promotion of content.

Content-free residual factors are a separate, default path: verified
factors with no source content may train `org:` and `world:` without
opt-in, subject to opt-out, the 1/64 floor, the waist cap, and a
minimum contributor count. See [residual factors](residual-factors.md).

## Scales and namespaces

The scale names are the pin names from
[cascade address](../200-core/cascade-address.md), mapped onto the
persona-store tiers from PR #31. One vocabulary is used.

| Pin / scale | Persona tier | Hub prefix |
| ----------- | ------------ | ---------- |
| individual  | individual   | `user:`    |
| local       | hub          | `org:`     |
| global      | latent       | `world:`   |

A draft of this module mapped local to `world:` and global to `org:`.
That is backwards in this repo. `hub_train.py` defines `user:` as
operator preferences, `world:` as a shared project / world, and
`org:` as a tenant. Guild hubs already live under `org:guild:...`.
The corrected walk is `user:ada` → `org:ada` → `world:ada`.

`to_scale` must be exactly one step outward. Skipping a scale is
refused. The global scale cannot promote further.

## Residuals

The persona store already stores only the residual against the tier
above when a fact is promoted on that store. This helper does not
write. Titanos `learn` stores a full fact at the new subject, not a
residual against the tier above. The [residual-factors](residual-factors.md)
path narrows that gap for the default factor path: Eat still writes a
triple, but the object is the factor aggregate, not source content.
The richer promote path is unchanged.

## Renames

See the rename table in [cascade address](../200-core/cascade-address.md).
The draft module `cascade_learn.py` is now `resileos.persona.promote`.
