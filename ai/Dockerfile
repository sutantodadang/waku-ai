# syntax=docker/dockerfile:1
FROM python:3.11-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /app /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python3 -c "import os,http.client; p=os.getenv('PORT','8001'); conn=http.client.HTTPConnection('localhost:'+p); conn.request('GET','/health'); resp=conn.getresponse(); exit(0 if resp.status==200 else 1)"

# Exec the venv directly — `uv run` would re-sync (incl. dev deps) at startup,
# which needs network + a writable FS and fails on locked-down deploy runtimes.
# Honor the platform-provided $PORT, defaulting to 8001.
CMD ["sh", "-c", "/app/.venv/bin/uvicorn ai_service:app --host 0.0.0.0 --port ${PORT:-8001}"]
