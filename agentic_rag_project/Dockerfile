FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Docling is a heavy optional extractor (adds several GB) — disabled by
# default; we use the lightweight extract_files_light.py instead.
ARG INSTALL_DOCLING=false
COPY pyproject.toml uv.lock ./
RUN pip install uv && \
    if [ "$INSTALL_DOCLING" = "true" ]; then \
        uv sync --frozen --no-dev --no-install-project --extra docling; \
    else \
        uv sync --frozen --no-dev --no-install-project; \
    fi
ENV PATH="/app/.venv/bin:$PATH"

COPY . .

EXPOSE 8058
EXPOSE 8501