# ── Stage 1: build dependencies ──────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install only the build-time system deps needed for native wheels.
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libffi-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy only dependency metadata first for layer caching.
COPY pyproject.toml ./
COPY src/ ./src/

# Build a wheel and install into a clean prefix.
RUN pip install --no-cache-dir --prefix=/install .


# ── Stage 2: runtime image ──────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL maintainer="SIGMAXIS x ENSAM — Project P5"
LABEL description="AI Test Plan Generator — provider-agnostic multi-agent REST API"

# Non-root user for security.
RUN groupadd --gid 1000 app && \
    useradd --uid 1000 --gid app --shell /bin/bash --create-home app

WORKDIR /app

# Copy installed packages from builder stage.
COPY --from=builder /install /usr/local

# Copy source (needed for editable-style imports registered via hatchling).
COPY src/ ./src/
COPY pyproject.toml ./

# Copy the .env.example as a template (real .env is injected at runtime).
COPY .env.example ./.env.example

# Switch to non-root.
USER app

# Expose the API port.
EXPOSE 8000

# Health check using the /health endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Default command: start the API server.
CMD ["uvicorn", "ai_testplan_generator.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
