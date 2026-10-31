FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core fonts-indic \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.10.7

WORKDIR /srv/app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
# Kept apart from the app's packages, because it is a third-party proxy.
RUN uv venv /opt/freellmpool \
    && uv pip install --python /opt/freellmpool freellmpool==0.13.0
COPY . .

# Separate users, so the proxy cannot read the API's secrets. start.sh runs as
# root only to fix the volume's ownership, then drops to these users.
RUN useradd --create-home --uid 1001 agent \
    && useradd --create-home --uid 1002 pool \
    && mkdir /data

# Mount a persistent volume at /data, or everything is lost on each deploy.
ENV DATABASE_PATH=/data/app.db \
    CHECKPOINT_PATH=/data/checkpoints.db \
    FILES_PATH=/data/files \
    PATH=/srv/app/.venv/bin:/opt/freellmpool/bin:$PATH

EXPOSE 8000
CMD ["sh", "start.sh"]
