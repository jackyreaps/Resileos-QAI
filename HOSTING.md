doc: RES-800
title: Hosting Guide
status: stable
depends_on: [RES-320, RES-321, RES-322]
referenced_by: []

# Hosting Guide

Deploy Resileos-QAI as a knowledge/query service. This is Titanos plus
the residual substrate plus the FastAPI console plus the Streamlit
dashboard. It is not a next-token generative LLM. Answers come from the
band store via query / chain / SPARQL; there is no free-text generation
head in this repository.

## 1. What runs

| Component | Port | Entry point |
|---|---|---|
| FastAPI backend | 8000 | `app:app` |
| Streamlit dashboard | 8501 | `ui.py` |
| Titanos band store | in-process | `scripts/titanos.py` |
| Residual substrate | in-process | `resileos.substrate` |

Single process. The Titanos store is a module-level singleton; replicas
must stay at 1 unless the store is externalized.

## 2. Quick start (Docker)

### 2.1 Clone and prepare the state file

    git clone https://github.com/jackyreaps/Resileos-QAI.git
    cd Resileos-QAI
    touch titanos_live_state.json

The `touch` matters. Docker creates a **directory** at the mount path
if the file does not exist. `app.py` expects a file and will fail to
read it.

### 2.2 Build

    docker compose build

### 2.3 Run

    docker compose up -d
    # API :8000
    # UI  :8501

### 2.4 Verify both probes

    curl -sf http://127.0.0.1:8000/api/v1/substrate_stats
    curl -sf http://127.0.0.1:8000/api/v1/ready

`/substrate_stats` confirms the residual core is loaded.
`/ready` returns 503 until the Titanos store is open. The container
healthcheck hits both.

### 2.5 Seed

`app.py` loads `configs/titanos-facts.json` once on first boot if the
store is empty and the live state file is absent. On a clean deploy,
`/ready` will show `facts > 0` with `seeded_from` set to the seed path.

To seed manually (or add to an existing store):

    curl -s -X POST http://127.0.0.1:8000/api/v1/learn \
      -H "Content-Type: application/json" \
      -d '{"subject":"alice","relation":"knows","obj":"bob"}'
    curl -s -X POST http://127.0.0.1:8000/api/v1/save

## 3. Smoke queries

Single hop:

    curl -s -X POST http://127.0.0.1:8000/api/v1/sparql \
      -H "Content-Type: application/json" \
      -d '{"query":"SELECT ?o WHERE alice --knows--> ?o"}'

Inverse:

    curl -s -X POST http://127.0.0.1:8000/api/v1/sparql \
      -H "Content-Type: application/json" \
      -d '{"query":"SELECT ?s WHERE ?s <--knows-- bob"}'

Multi-hop join:

    curl -s -X POST http://127.0.0.1:8000/api/v1/sparql \
      -H "Content-Type: application/json" \
      -d '{"query":"SELECT ?o WHERE alice --knows--> ?o AND ?o --works_at--> acme"}'

Full scan (requires `iter_entities` on the core):

    curl -s -X POST http://127.0.0.1:8000/api/v1/sparql \
      -H "Content-Type: application/json" \
      -d '{"query":"SELECT ?s, ?o WHERE ?s --knows--> ?o"}'

Open the dashboard at http://127.0.0.1:8501.

## 4. Production defaults

    phi_compress_enabled = False       # see docs/400-operations/phi-compress-closed.md
    replicas             = 1           # single-process store
    auth                 = required before public exposure
    healthcheck          = /substrate_stats AND /ready

## 5. Before public exposure

The following are not implemented and must be added upstream of the
container:

- **Auth.** There is no authentication in `app.py`. Put the service
  behind a reverse proxy or API gateway with token or session auth.
- **Rate limits.** None in-app. The reverse proxy or gateway must
  enforce them.
- **TLS.** Terminate at the reverse proxy.

Internal-only deployments (localhost, LAN) can run without these.

## 6. Development without Docker

    pip install -e ".[all]"
    bash run_system.sh

`run_system.sh` starts uvicorn and Streamlit together and installs the
package if it is not yet importable.

## 7. Persistence

`titanos_live_state.json` at repo root is the durable state. It is
written on every `/api/v1/learn` and `/api/v1/save` call. Docker
compose mounts it as a file (see §2.1). Back it up if the store
matters.

## 8. What this host is not

- **Not a generative LLM.** No next-token model in the repository.
  Answers are structured (query results, chain traversals, SPARQL
  rows). To produce prose, add a small template or an external model
  layer that consumes the query results.
- **Not horizontally scalable as-is.** The store is a module-level
  singleton. Multiple worker processes will each have their own view.
  To scale out, externalize the store (RES-320 §6 lists the path).
- **Not a quantum computer.** The substrate is a classical phase field
  with quantum-shaped mathematics (RES-308). No QPU is involved.

## 9. Read next

- [Documentation Index](docs/readme.md) — RES-000
- [Disk-Backed Band Store](docs/320-titanos/store.md) — RES-320
- [Query Language and Execution](docs/320-titanos/query.md) — RES-322
- [phi-compress closed](docs/400-operations/phi-compress-closed.md) — RES-401
