# Resileos-QAI container.
# Backend (FastAPI :8000) + dashboard (Streamlit :8501) in one image.
# requires-python >= 3.11, so the base image must be 3.11+.

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# curl for the healthcheck. build-essential is not installed by default;
# add it only if a dependency has to compile from source.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY . .
RUN pip install -e ".[all]"

EXPOSE 8000 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -sf http://localhost:8000/api/v1/substrate_stats >/dev/null || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]