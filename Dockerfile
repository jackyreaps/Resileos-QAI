FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates gnupg \
    && curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg \
        | gpg --dearmor -o /usr/share/keyrings/cloudflare-main.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" \
        > /etc/apt/sources.list.d/cloudflared.list \
    && apt-get update && apt-get install -y --no-install-recommends cloudflared \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Layer cache: deps first
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install -e ".[all]" || true

# App code second
COPY . .
RUN pip install -e ".[all]"

RUN useradd -m -u 10001 resileos && chown -R resileos:resileos /app
USER resileos

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -sf http://127.0.0.1:8000/api/v1/substrate_stats >/dev/null || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
