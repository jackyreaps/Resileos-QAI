---
doc: RES-328-persona-ui
title: Persona UI — Router Classes, Memory Strip, and HTTP Shapes
status: implemented
depends_on: [RES-328-router, RES-328-hub-ns, RES-400-hosted-mouth]
---

# Persona UI

The console is one chat column. The five router classes in
[chat-router.md](chat-router.md) are five behaviours. The right-hand strip
is the `user:<id>` ledger from `ask_list`. Subjects and relations are the
hub namespace: `user:`, `world:`, `org:`, and `prefers`, `stated`,
`setting`, `note`.

## 1. Class to UI

| Class | What the turn does | What the column shows |
|-------|--------------------|------------------------|
| `TOOL_FACT` | `resileos_ask` (`ask_list`) on a world or store subject | Plain answer. No chip when the status is `ACCEPTED`. |
| `HUB_LEARN` | `learn` into `user:<id>` only | The written triple, plus a memory chip. |
| `HUB_RECALL` | `ask_list` on a hub subject (`user:<id>` unless the text names `world:` or `org:`) | Hub-scoped answer. Rows only. |
| `SOFT_CHAT` | No tool | Mouth-only persona prose, and only when Metis `allow_mouth` is set. |
| `ABSTAIN_SURFACE` | No tool | Abstain chip and a teach affordance. |

Status chips render only when status is not `ACCEPTED`:

| Status | Chip |
|--------|------|
| `CONFLICT` | conflict |
| `ABSTAINED` | abstained |
| `NO_ROWS` | no rows |
| `ACCEPTED` | none |
| `MOUTH_CLOSED` | none (prose was withheld) |

`HUB_LEARN` with a confirmed write also shows a memory chip while status
stays `ACCEPTED`.

## 2. Decision order

First match wins.

1. Teach cue (`remember` / `learn` at the start, `remember that`, `I prefer`, `my X is`) → `HUB_LEARN`.
2. Hub-scoped question (`what do I …`, `in my workspace`, `about me`, a `user:` / `world:` / `org:` subject) → `HUB_RECALL`.
3. World or store fact (who / what / when / where, a known entity or relation, or `parse_query`) → `TOOL_FACT`.
4. A follow-up after an empty or abstained result → `ABSTAIN_SURFACE`.
5. Anything else → `SOFT_CHAT`.

`+ remember` on a message forces `HUB_LEARN` for that text.

## 3. Mouth

The chat page sends `prose: true`. That asks the route to render when
the gate allows. It does not open the factual mouth. The route ignores
a client `allow_mouth` flag. `should_render_prose(..., require_verified=True)`
stays the factual gate: an unverified cycle does not authorize an
assertive fact. Metis `allow_mouth` may open a non-factual persona line.

On a verified `TOOL_FACT`, `HUB_RECALL`, or `HUB_LEARN`, `render_persona_mouth`
expands only the structured rows, the persona pack, Aphrodite care
weights, and recent verified Hades lessons (lesson text only, under a
Hermes budget). The sentence is natural language. It does not add a
value that is not in those rows or lessons. The structured status and
rows are always returned beside the sentence.

`prose: false` leaves the mouth closed. The reply is the row strings,
or the bare triple after a learn, and does not add a sentence. An empty
result abstains in plain language and offers `remember that…`. It does
not invent a value. A conflict names every stored value and does not
pick one.

An unverified cycle uses a holding line (`Checking the record…`) and
does not state a stored value in the sentence.

`SOFT_CHAT` with prose off returns `reply_text: ""` and
`status: MOUTH_CLOSED`. With prose on and a verified cycle, the reply
is one persona line (`honest`, `guide`, `builder`, `mythic`) and no
store fact.

`HUB_LEARN` confirms the triple. The sentence form needs a verified
cycle and prose. The bare triple does not. Aphrodite may raise a care
weight on that object. She does not write a residual fact.

## 4. Memory strip

`GET /api/v1/hub/{hub_id}/ledger` lists current objects from `ask_list`
for every relation stored on `user:<id>`.

Empty state, exact copy:

```text
Nothing learned about you yet. Say "remember that…" to teach me.
```

`PUT` replaces one triple (`learn` after the old log row is removed).
`DELETE` removes one triple. Both refuse any subject that is not
`user:<id>`.

`scripts/tool_mouth_demo.py --hub-user alice` still learns the raw subject
`alice` on its own Titanos. The chat route writes `user:alice`, which is
the namespace the demo's docstring points at.

## 5. Request and response shapes

Auth on every route below: header `X-API-Key`. Missing or invalid keys
follow the existing fail-closed rules (`401`, `403`, or `503`).

### `POST /api/v1/chat`

Request:

```json
{
  "text": "what is the domain of Zeus",
  "hub_id": "alice",
  "force_class": null,
  "last_tool_empty": false,
  "persona": "honest",
  "prose": true
}
```

`force_class` is `null` or one of the five class names. `persona` is
`honest`, `guide`, `builder`, or `mythic` (anything else is treated as
`honest`). `prose` defaults to true. False keeps the closed mouth.
Sending `allow_mouth` does not force a fact.

Response:

```json
{
  "reply_text": "Zeus domain sky.",
  "status": "ACCEPTED",
  "router_class": "TOOL_FACT",
  "hub_id": "alice",
  "subject": "Zeus",
  "rows": ["sky"],
  "chip": null,
  "memory_chip": false,
  "teach_affordance": false,
  "persona": "honest",
  "allow_mouth": false,
  "action_taken": {
    "class": "TOOL_FACT",
    "action": "ask",
    "tool": "resileos_ask",
    "subject": "Zeus",
    "relation": "domain",
    "relations": ["domain"],
    "obj": null,
    "rows": ["sky"],
    "wrote": false,
    "inverse": false
  }
}
```

`status` is `ACCEPTED`, `CONFLICT`, `ABSTAINED`, `NO_ROWS`, or
`MOUTH_CLOSED`. `chip` is `null`, `"conflict"`, `"abstained"`, or
`"no_rows"`. `action` is `ask`, `learn`, `none`, or `abstain`.

`HUB_LEARN` sets `memory_chip` true, `wrote` true, `tool` `"learn"`, and
`subject` `user:<id>`. `ABSTAIN_SURFACE` sets `status` `ABSTAINED`,
`chip` `"abstained"`, `teach_affordance` true, and `action` `"abstain"`.
`NO_ROWS` and `ABSTAINED` also set `teach_affordance`, so an empty fact
or recall offers the same teach path.

### Hub ledger

`GET /api/v1/hub/{hub_id}/ledger`

```json
{
  "hub_id": "alice",
  "subject": "user:alice",
  "triples": [
    {
      "subject": "user:alice",
      "relation": "prefers",
      "obj": "exact_answers",
      "valid_from": null,
      "valid_to": null
    }
  ]
}
```

`PUT /api/v1/hub/{hub_id}/ledger`

```json
{
  "relation": "prefers",
  "obj": "exact_answers",
  "new_relation": "prefers",
  "new_obj": "short_answers"
}
```

Response is the ledger plus `"removed"` (int) and `"wrote"` (bool).
Unknown triple: `404`.

`DELETE /api/v1/hub/{hub_id}/ledger?relation=prefers&obj=exact_answers`

Response is the ledger plus `"removed"`. Unknown triple: `404`.

`<id>` is lowercase `[a-z0-9_]{1,64}` after a leading `user:` is stripped
and other characters are dropped.

### Studio

All bodies are JSON. Round-trip and sample responses include
`learned: false` and `scar_matrix_updated: false`. Numpy arrays are nested
lists.

| Method and path | Request | Response |
|-----------------|---------|----------|
| `GET /api/v1/studio/codecs` | — | `{"codecs": ["pca_component", "learned_conv"]}` |
| `POST /api/v1/studio/codecs/project` | `{"image": [[0, 1], [1, 0]], "m": 8, "n": 8}` | `{"shape": [8, 8], "image": [[...]]}` |
| `POST /api/v1/studio/candidates` | `{"kind": "image", "path": "candidate://x", "title": "CANDIDATE", "world_id": "studio", "note": ""}` | `register_candidate` dict: `ok`, `asset_id`, `kind`, `path`, `title`, `world_id`, `note`, `status: "candidate"`, `learned: false`, `learn_called: false` |
| `GET /api/v1/studio/service/prior` | — | `study_prior_report()` |
| `POST /api/v1/studio/service/round-trip` | `{"image": [[0, 1], [1, 0]], "codec_name": "pca_component"}` | `round_trip`: `codec`, `projected`, `decoded`, `metrics`, `packet`, `gate`, `status`, `learned`, `scar_matrix_updated`. Unknown codec `400`. Unavailable codec (`learned_conv`) `409`. |
| `POST /api/v1/studio/service/sample` | `{"label": 3, "seed": 0, "register": true}` | `sample_toy_prior` |
| `POST /api/v1/studio/gate` | `{"packet": { ... studio-codec/1 ... }}` | `gate_studio_packet` |
| `GET /api/v1/studio/panel` | — | `{"codecs", "prior", "sampler", "renderer": "resileos.studio.panel.render_residual_codec", "http_invokes_renderer": false}` |
| `GET /api/v1/studio/external-sampler` | — | `{"refused": bool, "risk": {"risk_class", "reason", "action"}, "sampler": {"enabled", "name", "reason"}}` |
| `POST /api/v1/studio/external-sampler` | `{"condition": {"prompt": "a hill", "seed": 0}, "register": true}` | `propose_external` plus `refused: false` and `risk`. `403` when `RESILEOS_EXTERNAL_SAMPLER` is unset or the sampler is off, and when `risk_classify` returns `deny`. |

### UI modules

Perception responses always include `candidates` (each `{triple, accepted, eat}`),
`written`, and `committed`. `written` is empty unless `commit` is true and
`eat_filter` accepted that triple.

| Method and path | Request | Response |
|-----------------|---------|----------|
| `POST /api/v1/perceive/image` | `{"image": [[0, 1], [1, 0]], "subject": "image", "commit": false}` | perception fields from `perceive_image` plus candidates |
| `POST /api/v1/perceive/art` | `{"title": "hymn", "description": "short", "world_id": "world:art", "commit": false}` | `encode_art` under `art`, plus candidates |
| `POST /api/v1/perceive/frame` | `{"image": [[0, 1], [1, 0]], "subject": "frame", "commit": false}` | `codec_summary` under `codec`, plus candidates |
| `POST /api/v1/perceive/audio` | `{"wave": [0.0, 0.2], "subject": "audio", "commit": false}` | `perceive_audio` under `perception`, plus candidates |
| `POST /api/v1/perceive/video` | `{"frames": [[[0, 1], [1, 0]]], "subject": "video", "commit": false}` | `perceive_video` under `perception`, plus candidates |
| `POST /api/v1/perceive/language` | `{"text": "hello", "subject": "text", "commit": false}` | `perceive_language` under `perception`, plus candidates |
| `POST /api/v1/generate/fluid` | `{"image": null, "belt": 0, "frame": 0, "persona": "", "subject": "frame"}` | `generate_still`: `embed`, `triple`, `prompt`, `still_url`, `backend` |
| `POST /api/v1/generate/local` | same shape | `generate_local`: `embed`, `field`, `triple`, `gate`, `pattern_shape`, `pattern`, `backend`, `note` |
| `POST /api/v1/generate/video` | `{"prompt": "a hill"}` | `generate_video_hook`. Unconfigured hosts return `status: UNAVAILABLE`, `url: null`, `draft: false` |
| `POST /api/v1/task/lookup` | `{"goal": "domain", "steps": [{"subject": "Zeus", "relation": "domain"}]}` | `task_with_scale`: `goal`, `trace`, `answer`, `scale`. Store lookups only |
| `POST /api/v1/language/detect` | `{"text": "hello"}` | `detect_language`: `guess`, `latin_share`, `other_share`, `address`, `note` |
| `POST /api/v1/language/translate` | `{"text": "hello", "target": "en", "source": null}` | `translate`: `text`, `translated`, `target`, `source`, `provider`, `address`, `note` |
| `POST /api/v1/agent/task` | `{"goal": "status", "steps": [{"tool": "git_status", "args": {}}]}` | `{"result": {...}, "harness": {...}}`. Mutating tools (`write_file`, `apply_diff`, `git_commit`) set `result.ran` false and `result.verification.requires_verification` true. They are not called. |
| `POST /api/v1/mouth/custom` | `{"rows": [{"subject": "Zeus", "relation": "domain", "obj": "sky"}], "question": ""}` | `custom_mouth.answer`: `text`, `backend`, `epistemic`, `row_count`, `scale` |
| `POST /api/v1/explain` | `{"query": "domain", "hub_rows": ["sky"]}` | `explain`: `text`, `source`, `query` |
| `POST /api/v1/remember` | `{"subject": "ada", "relation": "likes", "obj": "geometry"}` | `remember`: `subject` (`user:ada` if no hub prefix), `relation`, `obj`, `scale`. Does not `learn`. |

## 6. Not an HTTP call

| Function | Where it runs |
|----------|----------------|
| `studio.panel.render_residual_codec` | Streamlit gear drawer in `ui.py`. `GET /api/v1/studio/panel` returns the panel data and does not invoke the renderer. |
| `agent_loop` mutating tools | `POST /api/v1/agent/task` refuses `write_file`, `apply_diff`, and `git_commit`. |

## 7. CORS

`asgi:app` allows `https://resileosai.fun` and `https://www.resileosai.fun`.
`RESILEOS_CORS_ORIGINS` (comma-separated) replaces that list. Methods:
`GET`, `POST`, `PUT`, `DELETE`, `OPTIONS`.
