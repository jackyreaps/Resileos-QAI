# Security Policy

## Reporting a vulnerability

Open a private security advisory on this repository. Do not open a public issue for vulnerabilities.

## Scope

- FastAPI backend (`app.py`, `asgi.py`)
- Streamlit console (`ui.py`)
- Authentication middleware (`middleware/auth.py`)
- Docker deployment (`Dockerfile`, `docker-compose.yml`, `docker-entrypoint.sh`)

## Deployment invariants

- The backend and UI bind to `127.0.0.1` only.
- No host ports are published. Ingress is via an outbound Cloudflare Tunnel.
- All API routes except `/healthz`, `/api/v1/ready`, and `/docs` require an API key.
- The API key file is mounted read-only.

## Known non-issues

- The quantum backend is a labeled classical simulation (`QUANTUM_SIM`). It makes no cryptographic or speedup claims.
- The Titanos store is a single-process singleton. Horizontal scaling requires externalizing the store (RES-320 §6).
- The `titanos_live_state.json` file is bind-mounted from the host and **must be writable by uid 10001**. `chmod 666` is the documented default for single-user hosts. On a shared host, use `chown 10001:10001` + `chmod 644` instead, or migrate to a named volume:

  ```yaml
  volumes:
    - resileos_state:/app/titanos_live_state.json
  ```

  The bind mount exists so the state file is directly editable from the host for debugging. If that convenience is not needed, the named volume is strictly more secure.
