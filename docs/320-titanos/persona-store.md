# Persona store

The tutorial and the persona mouth start from this store. It is not Titanos and it does not update the scar matrix. Eat stays Eat.

Three tiers. Data moves individual → hub → latent only when someone opts in at that step.

| Tier | What it is | Who can read it |
|---|---|---|
| Individual | Private memory for one account, or one signed-out session | That principal only |
| Hub | One chartered guild, subject `org:guild:<id>` | Seated members of that guild |
| Latent | Shared frame above guilds. It starts as the self-facts seed | The seed is shared. Promoted rows are shared lessons, never personal facts |

The individual tier is not a hub. Chat still sends `hub_id`. Until accounts land, that field is an opaque user id. `anon` stores nothing.

## Files

```text
configs/persona/self_facts.json          seed (latent starting frame)
data/persona/individuals/account/<id>.json
data/persona/individuals/session/<id>.json
data/persona/guilds/<guild_id>.json
data/persona/latent/promoted.json
```

`data/persona/` is runtime state. Edit the seed in git. Do not put API keys in any of these files.

## Residual frames

A tier stores only what differs from the tier above it.

- The latent frame is the seed plus residuals that a guild steward promoted.
- A guild hub stores the residual of its shared frame against that latent frame.
- An individual frame stores the residual of what that person said against the latent frame, or against the latent frame composed with the hubs they sit in.

`stated` on an individual file is the private list they can view, edit, and delete. `residual` is the derived frame. Both live in this store. Promoting a fact does not delete the private statement. It drops the residual cell once the tier above already holds the same text.

User cells are labeled `user-stated`. Seed cells are labeled `verified-seed`. The mouth does not treat a user cell as a verified world fact. If a name, goal, or skill was never stated, the reply abstains.

## Opt-in

`put` never promotes. `POST /api/v1/persona/promote` with `opt_in: true` moves one fact one tier.

- Individual → hub requires a seat in that guild (moniker, local rank).
- Hub → latent requires a local `steward` rank (RS-INF-003 ladder: initiate, member, journeyman, senior, steward), `opt_in: true`, and a residual that recurs across members.
- Kinds `name`, `goal`, `skill`, `preference`, `stated`, and `tutorial` are personal. They can sit on a guild hub the member opted into. They cannot enter latent.
- A `shared` fact can enter latent only when `personal` is false, at least two seated members stated the same text, and a steward opts in.

Nothing in this path calls `learn`, `ResidualCore`, or `join_guild`.

## Frame reflection (gnosis is unfilled)

Upward reflection stays opt-in and residual-based. A steward promotes a residual that recurs across seated members. `holders` is that count. It is not a rank, and it is not a score of anyone's beliefs. `FrameReflection` in `src/resileos/persona/reflection.py` is the extension point. `gnosis` stays `unfilled`.

The owner source called gnosis is not available. The public reading to fill later is [QD-TER Human Medium, Agency and Gnosis](https://github.com/jackyreaps/QD-TER-Human-Medium/blob/main/docs/agency_and_gnosis_architecture.md) and `adjacent/gnosis_frame.md`: a frame is carried upward, and the residue is what remains when that carry is sustained. Replace `FrameReflection.recurring` when that source can be wired. Do not import it here.

The stored frame follows the Frame Atlas drafts (owner, unpublished). Those drafts are not in this repo. Each tier stores one frame with four parts: axes (independent criteria kept in view), a verdict space (accept, abstain, refuse), a scope (the cases it covers), and non-claims (what it does not settle). Stored tiers keep the axes `statement`, `source`, and `limit` apart.

Four properties are reported beside those parts and are never merged into one score: dimensionality (the number of axes), level (nested order: root 0, latent 1, hub 2, individual 3), openness (whether it can be shown wrong, and how), and genealogy (its relation to the meta-aware root). More axes or a different level is not truer.

The meta-aware root does five things. It recognizes a frame as a frame, keeps axes distinct until a stated reason forces combining them, states non-claims, may abstain without counting that as failure, and applies the same tests to itself (`MetaAwareRoot.self_check`). A frame stays a frame only while it is named, limited, and correctable.

The collapse check runs before a residual is written upward. It refuses the promotion, returns `ABSTAINED` with `failure: false`, and does not write when axes are merged without a stated reason, a lower non-claim is missing, or an open frame would become closed. A stated `axis_merge_reason` is what allows a combine. The default frames keep the same axes, keep every lower non-claim, and stay open, so an ordinary opt-in still promotes. The HTTP API does not accept a client frame.

`src/resileos/latent_hub.py` is the language hub. Its interface is `encode`, `bind_bundle`, `put`, `get`, and `nearest` on hypervectors. It is not a fact store, and `nearest` is a similarity score, so this path never calls those methods and never ranks a statement that way. `writes_latent_hub` stays false. `PersonaStore.latent_hub().read(scope)` reads this store's own residual (`self`, `promoted`, or `all`) as `{id, text, label, source}`. The two stay separate.

## Guild names this tier reuses

Policy stays in [guild-system](https://github.com/jackyreaps/guild-system). This file does not copy the Compact.

- GS-FND-002 Compact. Guild records store `compact_ref`.
- GS-CHR-010 Local Guild Charter. `charter_ref` defaults to that id. `frame_profile_ref` is the name `meta.frame_profile` from RS-INF-002. This store does not write the Titanos ledger.
- GS-CHR-011 moniker, local to the guild. The seat key is moniker plus the opaque individual id.
- RS-INF-003 ranks, as labels only. A local `steward` rank is not a Convocation, Imperium, or Sovereignty office (GS-CHR-012).

`org:guild:<id>` matches `guild_subject` in `src/resileos/answer/guild.py`. Seats here are not `join_guild` triples.

Individual frames sit under larger frames the way the human-medium layer describes a local node against a wider field ([QD-TER Human Medium](https://github.com/jackyreaps/QD-TER-Human-Medium)). The stored difference is the residual. It is not the residual core's scar matrix.

## API and the UI hook

Auth matches the rest of the API (`X-API-Key`).

- `GET /api/v1/persona/self` — seed version, facts, tutorial steps
- `GET /api/v1/persona/individual?account_id=` or `session_id=` — stated facts and the residual
- `PUT /api/v1/persona/individual/{fact_id}` — body `{text, kind, personal}`
- `DELETE /api/v1/persona/individual/{fact_id}`
- `GET /api/v1/persona/recall`
- `GET /api/v1/persona/hub/{guild_id}` — members only
- `POST /api/v1/persona/hub/{guild_id}/seat` — local roster only
- `POST /api/v1/persona/promote` — `{guild_id, fact_id, to: hub|latent, opt_in}`

`X-Resileos-Account` must match `account_id` when the header is sent. Signed-out sessions expire (default 24 hours, `RESILEOS_PERSONA_SESSION_TTL_S`).

The persona routes (`/api/v1/persona/individual`, `/api/v1/persona/recall`) are admin-only on the API (`middleware/proxy_identity.py`); no site page calls them (the unused `persona-hook.js` helper was removed). Chat can send `persona: name Ada`, `persona: goal …`, `persona: skill …`, `persona: shared <id> <text>`, or `persona: forget <id>`. Those lines do not teach Titanos.

The mouth attaches `persona_recall` when it renders. A chat turn attaches the same packet, including the next seed tutorial step. A verified tutorial fragment records `progress_<step>` as user-stated. It does not write a residual fact through Aphrodite.

## Editing the seed

`configs/persona/self_facts.json` has `version` (integer ≥ 1), `updated`, `facts`, and `tutorial`.

Each row needs `id`, `text`, `check`, and `needle`. Facts also need `topic` (`capability`, `kin`, `limit`, `keys`). Tutorial rows need `label`. `check` is a path in this repo. `needle` is a short string that must appear in that file. Tests load the seed and check every needle.

Bump `version` when a row changes. Keep each `text` to one or two sentences. Do not add a frontier-model claim, a video URL, or a renamed Eat.
