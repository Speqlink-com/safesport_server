FROM ghcr.io/astral-sh/uv:0.11.16 AS uv
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY . .
EXPOSE 8000
CMD ["sh", "-c", "uv run --no-sync alembic upgrade head && uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]
