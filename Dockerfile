# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /app

# ── deps layer: cached unless the lockfile changes ───────────────────────────
FROM base AS deps
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# ── dev: includes test/lint tooling; what `make check` runs in ───────────────
FROM base AS dev
COPY --from=deps /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen
COPY . .

# ── runtime: no build tools, no dev deps, non-root ───────────────────────────
FROM base AS runtime
COPY --from=deps /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH=/app/src
COPY src/ /app/src/
COPY alembic/ /app/alembic/
COPY alembic.ini /app/
RUN useradd --uid 10001 --no-create-home topos && chown -R topos:topos /app
USER topos
EXPOSE 8000
