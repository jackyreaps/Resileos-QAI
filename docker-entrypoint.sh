#!/usr/bin/env bash
set -euo pipefail

BACKEND_PORT="${BACKEND_PORT:-8000}"
UI_PORT="${UI_PORT:-8501}"

log() { printf '[entrypoint] %s\n' "$*" >&2; }

# Outbound-only tunnel. No inbound ports are opened on the host.
if [[ -n "${TUNNEL_TOKEN:-}" ]]; then
    log "Launching Cloudflare Tunnel (outbound-only)..."
    cloudflared tunnel --no-autoupdate run --token "$TUNNEL_TOKEN" &
    TUNNEL_PID=$!
    trap 'kill -TERM "$TUNNEL_PID" 2>/dev/null || true' EXIT
else
    log "TUNNEL_TOKEN not set; running local-only."
fi

# Single process. The Titanos store is a module-level singleton.
log "Starting FastAPI on 127.0.0.1:${BACKEND_PORT}..."
uvicorn asgi:app \
    --host 127.0.0.1 \
    --port "$BACKEND_PORT" \
    --workers 1 \
    --proxy-headers \
    --forwarded-allow-ips "127.0.0.1" &
BACKEND_PID=$!

# Wait for liveness before starting Streamlit.
for _ in $(seq 1 60); do
    if curl -sf "http://127.0.0.1:${BACKEND_PORT}/healthz" >/dev/null; then
        break
    fi
    sleep 1
done

log "Starting Streamlit on 127.0.0.1:${UI_PORT}..."
exec streamlit run ui.py \
    --server.port "$UI_PORT" \
    --server.address 127.0.0.1 \
    --server.headless true \
    --server.enableCORS false \
    --server.enableXsrfProtection true
