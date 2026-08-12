FROM node:26-bookworm-slim AS frontend

WORKDIR /src/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.14-slim-bookworm AS runtime

COPY --from=ghcr.io/astral-sh/uv:0.10.3 /uv /uvx /bin/
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
COPY backend/README.md ./README.md
COPY backend/app ./app
RUN uv sync --frozen --no-dev
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./alembic.ini
COPY --from=frontend /src/frontend/build ./static

ENV PATH="/app/.venv/bin:$PATH" \
    BUILDABLE_DATA_DIR=/data \
    BUILDABLE_FRONTEND_DIR=/app/static

EXPOSE 8000
CMD ["fastapi", "run", "app/main.py", "--host", "0.0.0.0", "--port", "8000"]
