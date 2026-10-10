---
doc: RES-605
title: leCore Integration Bridge
status: stable
depends_on: [RES-300, RES-602]
referenced_by: []
---

# leCore Integration Bridge

`src/resileos/integration/lecore_client.py` gives Resileos-QAI the
ability to call leCore's standalone service as a capability router.
This is an **outbound** integration: Resileos consults leCore; leCore
does not need to know Resileos exists.

Direction is one-way:

    Resileos  ──►  leCore HTTP service

The reverse direction (leCore calling Resileos as a faculty, or leOS
routing to Resileos as a bone) is a separate integration. That side
lives in the leOS repository and is not part of this document.

## 1. Contract

leCore's service exposes (per its SERVICE.md):

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Liveness + version |
| `/capabilities` | GET | Names of advertised faculties |
| `/capabilities/search` | POST | Ranked matches for a query string |
| `/tools` | GET | Manifest with descriptions and params |
| `/invoke` | POST | Run one faculty with arguments |

Resileos wraps these in `LeCoreClient` with typed methods:

| Method | Wraps | Failure mode |
|---|---|---|
| `health()` | `GET /health` | raises `LeCoreUnreachable` / `LeCoreError` |
| `capabilities()` | `GET /capabilities` | same |
| `tools()` | `GET /tools` | same |
| `search(query)` | `POST /capabilities/search` | same |
| `invoke(name, args)` | `POST /invoke` | soft-fail: `InvokeResult(ok=False, ...)` |
| `is_available()` | `GET /health` | returns `bool`, never raises |

`invoke` is intentionally soft-failing so it can be used as a
best-effort capability by callers that do not want to branch on
leCore's presence. `search` is intentionally hard-failing so the
caller decides how to handle leCore being down.

## 2. Configuration

| Environment variable | Default | Meaning |
|---|---|---|
| `LECORE_URL` | `http://127.0.0.1:8080` | Service base URL |
| `LECORE_TOKEN` | unset | Bearer token if the service was launched with `--token` |
| `LECORE_TIMEOUT` | `15` | Seconds per request |

## 3. HTTP surface in Resileos

`POST /api/v1/lecore/route` — send a task description, get ranked
capability homes. Soft-fails: returns `{"available": false, "error": ...}`
when leCore is not reachable, rather than a 5xx. A UI can therefore
display the substrate normally whether or not leCore is up.

`GET /api/v1/lecore/health` — liveness probe for the leCore service.

## 4. What this is not

- Not a substrate merge. Resileos uses MAP (Multiply-Add-Permute);
  leCore uses HRR (circular convolution / correlation). The two are
  not algebraically interchangeable. This bridge calls leCore's
  faculties as black boxes; it does not replace Resileos's substrate.
- Not the reverse-direction integration. That is a separate file
  (`leos_titanos_tool.py`) that lives in the leOS repository.
- Not a claim that leCore is required. Resileos runs standalone. When
  leCore is absent, `available` is `false` and everything else works.

## 5. Reproduce

    # Start leCore's service in a separate terminal
    leos-core[service]        # or however the service is launched

    # From Resileos
    curl -X POST http://localhost:8000/api/v1/lecore/route \
         -H "Content-Type: application/json" \
         -d '{"query": "compress a float series"}'

Response (when leCore is up):

    {
      "available": true,
      "query": "compress a float series",
      "capabilities": [
        {"name": "...", "description": "...", "score": 0.91},
        ...
      ]
    }

Response (when leCore is down](../):

    {
     500 "available": false,
      "error": "GET /health: ..."
    }

## Read next

- [Two-Head Integration Note](integration.md) — RES-602
- [Roadmap-notes/roadmap.md) — RES-501
