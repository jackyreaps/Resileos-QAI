# Welcome to Resileos

You have an API key. This walks you from zero to a working query in about five
minutes. Every endpoint below is live on the hosted API.

Replace `api.yourdomain.dev` with the URL you were given. Replace `<your key>`
with the key from your welcome email.

## 1. Your key

Send it on every request as `X-API-Key: <your key>` or
`Authorization: Bearer <your key>`.

Do not commit it. Do not paste it into a chat, an issue tracker, or a pastebin.

## 2. Check the API is up

```bash
curl -s https://api.yourdomain.dev/api/v1/ready
```

Expected response:

```json
{"ready": true, "facts": 0, "answer_backend": "structured", "auth_required": true}
```

`/api/v1/ready` is public by design so monitoring can reach it. Everything else
requires the key.

## 3. Learn a fact

```bash
curl -s -X POST https://api.yourdomain.dev/api/v1/learn \
  -H "X-API-Key: <your key>" \
  -H "Content-Type: application/json" \
  -d '{"subject":"alice","relation":"works_at","obj":"acme"}'
```

Expected response:

```json
{"status": "SUCCESS", "records": 1}
```

## 4. Query it back

```bash
curl -s -X POST https://api.yourdomain.dev/api/v1/query \
  -H "X-API-Key: <your key>" \
  -H "Content-Type: application/json" \
  -d '{"subject":"alice","relation":"works_at"}'
```

Expected response:

```json
{"value": "acme", "status": "ACCEPTED", "confidence": 1.0, "mode": "CLASSICAL"}
```

## 5. Query something you never learned

```bash
curl -s -X POST https://api.yourdomain.dev/api/v1/query \
  -H "X-API-Key: <your key>" \
  -H "Content-Type: application/json" \
  -d '{"subject":"bob","relation":"works_at"}'
```

Expected response:

```json
{"value": null, "status": "ABSTAINED", "confidence": 0.0}
```

This is the product. The store does not invent. An empty answer is an honest
answer.

## 6. Batch load

```bash
curl -s -X POST https://api.yourdomain.dev/api/v1/learn_batch \
  -H "X-API-Key: <your key>" \
  -H "Content-Type: application/json" \
  -d '{"facts":[["alice","works_at","acme"],["acme","located_in","nyc"]]}'
```

Use batch for anything above a handful of facts. It rebuilds the index once per
batch instead of once per fact.

## 7. Multi-hop

```bash
curl -s -X POST https://api.yourdomain.dev/api/v1/chain \
  -H "X-API-Key: <your key>" \
  -H "Content-Type: application/json" \
  -d '{"start":"alice","relations":["works_at","located_in"]}'
```

Expected response:

```json
{"value": "nyc", "status": "ACCEPTED", "path": ["alice", "acme", "nyc"]}
```

## 8. SPARQL-like queries

```bash
curl -s -X POST https://api.yourdomain.dev/api/v1/sparql \
  -H "X-API-Key: <your key>" \
  -H "Content-Type: application/json" \
  -d '{"query":"SELECT ?o WHERE alice --works_at--> ?o"}'
```

Also supported:

- `SELECT ?s WHERE ?s <--works_at-- acme`
- `SELECT ?o WHERE alice --works_at--> ?o AND ?o --located_in--> nyc`
- `SELECT ?s, ?o WHERE ?s --works_at--> ?o`

## 9. One-sentence answers (optional)

```bash
curl -s -X POST https://api.yourdomain.dev/api/v1/answer \
  -H "X-API-Key: <your key>" \
  -H "Content-Type: application/json" \
  -d '{"subject":"alice","relation":"works_at"}'
```

`/api/v1/answer` returns both the rows and a rendered sentence. The rows are
authoritative; the sentence is a rendering of them.

## 10. Tool schemas for external agents

```bash
curl -s https://api.yourdomain.dev/api/v1/tools \
  -H "X-API-Key: <your key>"
```

Returns OpenAI-compatible tool schemas so an external model can call the store
as a tool instead of being given facts in a prompt.

## 11. Quotas and rate limits

Every response carries:

| Header | Meaning |
|---|---|
| `X-Usage-Count` | Requests used this month |
| `X-Usage-Quota` | Monthly limit for your key |
| `X-RateLimit-Remaining` | Requests left this minute (default 60/min) |

Exceeding the monthly quota returns `429`. There is no silent overage.

## 12. Persisting deliberately

Writes are persisted automatically. `POST /api/v1/save` forces a flush if you
want an explicit checkpoint before a maintenance window.

## 13. Not yet available on the hosted API

The repository contains guild and world-asset modules, but these routes are not
mounted on the hosted API:

- `POST /api/v1/guild/*`
- `POST /api/v1/world/register`

Do not build against them yet. They will be announced and documented here when
they are live.

## 14. Support

Reply to the email that delivered this key. One business day.
