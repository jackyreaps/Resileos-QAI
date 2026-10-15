#!/usr/bin/env bash
# Container entrypoint: backend in background, wait for readiness,
# dashboard in the foreground (so container lifecycle tracks the UI).

set -euo pipefail

BACKEND_PORT="${BACKEND_PORT:-8000}"
UI_PORT="${UI_PORT:-8501}"

echo "[entrypoint] backend on :$BACKEND_PORT"
uvicorn app:app --host 0.0.0.0 --port "$BACKEND_PORT" &

echo "[entrypoint] waiting for /api/v1/substrate_stats ..."
for _ in $(seq 1 60); do
    if curl -sf "http://localhost:$BACKEND_PORT/api/v1/substrate_stats" >/dev/null; then
        echo "[entrypoint] backend ready"
        break
    fi
    sleep 1
done

echo "[entrypoint] dashboard on :$UI_PORT"
# --server.address 0.0.0.0 and --server.headless true are required in a
# container. Without them Streamlit binds to localhost and refuses to run.
exec streamlit run ui.py \
    --server.port "$UI_PORT" \
    --server.address 0.0.0.0 \
    --server.headless true