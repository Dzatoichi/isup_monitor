FROM python:3.13-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:0.12.9 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project
RUN playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

COPY README.md alembic.ini ./
COPY migrations/ migrations/
COPY src/ src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable \
    && useradd --create-home --shell /usr/sbin/nologin appuser

USER appuser

ENTRYPOINT ["sh", "-c", "alembic upgrade head && exec isup-monitor \"$@\"", "--"]
CMD ["--save-db"]
