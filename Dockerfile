# Resileos-QAI container: FastAPI (loopback :8000) + Streamlit (loopback :8501).
# The container publishes no host ports. Ingress is via Cloudflare Tunnel.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

ARG TARGETARCH=amd64

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates \
    && curl -fsSL -o /usr/local/bin/cloudflared \
        "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${TARGETARCH}" \
    && chmod +x /usr/local/bin/cloudflared \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install --upgrade pip && pip install -e ".[all]"

COPY . .
RUN pip install -e ".[all]" \
    && mkdir -p /app/data \
    && useradd -m -u 10001 resileos \
    && chown -R resileos:resileos /app

USER resileos

# Documentation only. Do not publish these with `ports:`.
EXPOSE 8000 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD curl -sf http://127.0.0.1:8000/healthz >/dev/null \
        && curl -sf http://127.0.0.1:8000/api/v1/ready >/dev/null \
        || exit 1

ENTRYPOINT ["bash", "/app/docker-entrypoint.sh"]
