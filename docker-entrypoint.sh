#!/usr/bin/env bash
set -euo pipefail

BACKEND_PORT="${BACKEND_PORT:-8000}"
UI_PORT="${UI_PORT:-8501}"

# Outbound-only tunnel (no inbound ports)
if [[ -n "${TUNNEL_TOKEN:-}" ]]; then
    cloudflared tunnel --no-autoupdate run --token "$TUNNEL_TOKEN" &
    trap 'kill -TERM $! 2>/dev/null || true' EXIT
fi

uvicorn app:app --host 127.0.0.1 --port "$BACKEND_PORT" &
BACKEND_PID=$!

for _ in $(seq 1 60); do
    curl -sf "http://127.0.0.1:$BACKEND_PORT/api/v1/substrate_stats" >/dev/null && break
    sleep 1
done

exec streamlit run ui.py \
    --server.port "$UI_PORT" \
    --server.address 127.0.0.1 \
    --server.headless true
