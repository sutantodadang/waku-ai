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
    CMD python3 -c "import http.client; conn=http.client.HTTPConnection('localhost:8001'); conn.request('GET','/health'); resp=conn.getresponse(); exit(0) if resp.status==200 else exit(1)"

CMD ["uv", "run", "uvicorn", "ai_service:app", "--host", "0.0.0.0", "--port", "8001"]
