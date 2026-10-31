# Build from the repo root: docker build -f modules/language/Dockerfile -t gz-language .
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.10.7

WORKDIR /srv/app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY contracts ./contracts
COPY common ./common
COPY modules/__init__.py ./modules/__init__.py
COPY modules/language ./modules/language

RUN useradd --create-home --uid 1003 language
USER language
ENV PATH=/srv/app/.venv/bin:$PATH LOG_DIR=/tmp/logs

EXPOSE 8081
CMD ["sh", "-c", "uvicorn modules.language.app:app --host 0.0.0.0 --port ${PORT:-8081}"]
