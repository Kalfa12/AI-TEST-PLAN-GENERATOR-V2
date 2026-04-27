FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

FROM base AS builder
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md* ./
COPY src/ ./src/
RUN pip install --upgrade pip && pip install . && pip install "uvicorn[standard]"

FROM base AS runtime
RUN useradd --uid 10001 --create-home aitpg
COPY --from=builder /usr/local /usr/local
COPY --from=builder /app /app
USER aitpg
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=30s CMD \
    python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)" || exit 1
CMD ["uvicorn", "ai_testplan_generator.api.app:create_app", \
     "--factory", "--host", "0.0.0.0", "--port", "8000"]
