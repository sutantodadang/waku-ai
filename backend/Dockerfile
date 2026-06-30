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

# Create data directory for SQLite
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
