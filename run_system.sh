#!/usr/bin/env bash
# Launch the Resileos-QAI console: FastAPI backend + Streamlit dashboard.
# Dev convenience wrapper. For a reproducible env, use the Dockerfile.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

BACKEND_PORT="${BACKEND_PORT:-8000}"
UI_PORT="${UI_PORT:-8501}"
LOG_FILE="${LOG_FILE:-backend.log}"

BACKEND_PID=""

cleanup() {
    if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        # --reload spawns a child; kill the tree, not just the parent
        pkill -TERM -P "$BACKEND_PID" 2>/dev/null || true
        kill -TERM "$BACKEND_PID" 2>/dev/null || true
        wait "$BACKEND_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

echo "== Resileos-QAI =="

if ! python -c "import resileos" 2>/dev/null; then
    echo "[setup] installing package (editable, extras: all)"
    pip install -e ".[all]"
fi

echo "[backend] uvicorn app:app on :$BACKEND_PORT (log -> $LOG_FILE)"
uvicorn app:app --port "$BACKEND_PORT" --reload >"$LOG_FILE" 2>&1 &
BACKEND_PID=$!

echo "[backend] waiting for /api/v1/substrate_stats ..."
for _ in $(seq 1 60); do
    if curl -sf "http://localhost:$BACKEND_PORT/api/v1/substrate_stats" >/dev/null; then
        echo "[backend] ready"
        break
    fi
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo "[backend] died. Last lines of $LOG_FILE:" >&2
        tail -n 40 "$LOG_FILE" >&2 || true
        exit 1
    fi
    sleep 1
done

echo "[ui] streamlit ui.py on :$UI_PORT"
echo "[ui] open http://localhost:$UI_PORT"
echo "[ui] Ctrl-C to stop both."
streamlit run ui.py --server.port "$UI_PORT"