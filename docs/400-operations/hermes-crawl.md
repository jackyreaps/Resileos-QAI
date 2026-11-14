# Hermes crawl and Add facts

## What runs

| Piece | Kin / name | Does | Never |
|---|---|---|---|
| Native search | `hermes.native_search` (Agoraios) | BM25 over **our own** crawl index (`RESILEOS_HERMES_INDEX`, default `data/hermes_index.jsonl`) | call an outside service |
| Fallback | `SearchFallback` interface, `DuckDuckGoFallback` | Used only when the index has no match **and** `RESILEOS_SEARCH_FALLBACK=duckduckgo` is set. Packets say `origin: fallback:duckduckgo`, labelled "Third-party fallback" in the trail | run by default |
| Buzz | `hermes.pheme_buzz` (Pheme) | rising terms and entity pairs → next-wave query hint | become a fact (`is_fact: false`) |
| Fan-out | `hermes.ichnaea_fanout` (Ichnaea) | follows packets to origin pages through `assist.guarded_fetch` (public IPs only, connects to the checked IP), extracts claim spans with `source`, `span`, `as_of`, `valid_from`, `valid_to`; adds pages to our index | open private/loopback hosts |
| Eat bridge | `hermes_crawl.eat_bridge` | every candidate → `check_envelope` → `eat_filter`; commit path is `eat_commit_envelopes` → Zeus reviewers (`SeparatedCycle`) → Titanos | write directly; let prose through |
| Trace | `iris.crawl_trace` | reads the crawl audit JSONL (`RESILEOS_HERMES_TRACE`), counts only | write |
| Notes | Hades `HadesNotes` | one lesson-only line when a wave is noisy (≥ half held back) | store page text |

All Hermes/Iris legions are generators: registered via `kin/legions.register_legion`
with `writes_residual: False`, no `learn_fn` (the Kin gate refuses one), and
the usual risk + budget gate. Registration is off unless
`register_hermes_crawl_legions(enable=True)` is called.

Packets carry `url`, `domain`, `retrieved_at`, `tier`, `snippet`. `tier`
(institutional / reference / commercial / unknown) is for audit and routing
only. It is never a truth weight, and it never reaches Eat: `check_envelope`
reads only the claim fields and strips attention keys (likes, rank, views…).

## Quintuples and the cascade (interpretation)

- Quintuple = `(subject, relation, object, valid_from, valid_to)`. A bare
  triple is frame **3** (edge). A quintuple with at least one bound is
  frame **5** (belt).
- Wave depth `d` runs frames `(3, 5, 9, 12)[:d]`. Wave *i* asks the index
  for up to that frame's count and follows up to that many origin pages.
  The next wave's query adds the top Pheme term (routing only).
- PHI ranking: results are ordered by `relevance × φ^-(frame-3)` for the wave's frame (3/5/9/12; the frame's φ address relative to frame 3 = 1, an address, not a gain or a halving). Only a result whose own relevance is under 1/64 is dropped, at any wave, so wave-4 (frame 12) results stay. `weight` is the order key normalised to the best
  score. Anything under `EPSILON = 1/64` is dropped; at most `WAIST = 36` are kept.
- Only structured claims (schema.org JSON-LD on the page) become
  quintuples. Sentences become prose claims and Eat abstains on them
  (`unstructured_prose`).
- Bounds survive acceptance: `eat_commit_envelopes` passes
  `valid_from`/`valid_to` to `Titanos.learn`.

## Chat

Chat search now asks our index first (`assist.native_chat_search`,
`agent_loop._maybe_search`, and the runtime `hermes.web_search` legion all
go through `hermes_crawl.search_results`). The trail reads e.g.
"Searched 6 sources, followed 3 to the original pages, kept 2 facts", with
the facts and their sources under Details. Chat never saves them.

With an empty index and no fallback, chat says "Searched our index:
nothing found". Admins fill the index with `POST /api/v1/hermes/crawl`
(`urls` to read, optional `query` + `depth` to run waves). That endpoint is
admin-only and only previews facts.

## Admin → Knowledge → Add facts

One drop zone + one paste box + "Use from My files". Accepts `.txt`, `.md`,
`.csv`, `.json`, `.lean`.

1. Read the text (files are read in the browser; My files are fetched from the account's own Files).
2. `.lean`: checked with Lean. If it checks, each `theorem`/`lemma` becomes a candidate `(name, proved_in, Lean 4)`.
3. Pull out rigid facts: `a | b | c [| from | to]`, markdown table rows, `(a, b, c)`, CSV rows, JSON objects or lists.
4. `POST /api/v1/knowledge/preview`: `check_envelope` per fact, stored-fact conflicts, in-batch conflicts, already saved. Nothing is written.
5. The admin ticks facts and confirms. `POST /api/v1/knowledge/commit` (`confirm: true` required) → `eat_commit_envelopes` → reviewers → Titanos.

Plain per-item status: "Proof checks, 1 fact ready to save", "2 facts ready
to save; held back 1 (not clear facts)", "1 conflict with an existing fact",
then "Saved 4 facts". Both endpoints are admin-only on the Pages proxy and
on the API (`middleware/proxy_identity.py`).

## Left out

- The browser-use legion (driving a real browser for crawl) is roadmap, not built.
- PDF text extraction.
- No new outside search service; the only fallback wraps the existing DuckDuckGo helper and is off by default.
