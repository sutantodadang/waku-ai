# syntax=docker/dockerfile:1
FROM python:3.11-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy the rest of the app
COPY . .

# Sync again to install our package
RUN uv sync --frozen --no-dev

# Runtime stage
FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /app /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

EXPOSE 8000

# Exec the venv directly — `uv run` would re-sync (incl. dev deps) at startup,
# which needs network + a writable FS and fails on locked-down deploy runtimes.
# Honor the platform-provided $PORT, defaulting to 8000.
CMD ["sh", "-c", "/app/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
