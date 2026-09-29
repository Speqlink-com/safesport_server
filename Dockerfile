FROM ghcr.io/astral-sh/uv:0.11.16 AS uv
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
COPY --from=uv /uv /uvx /bin/
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 libxcb1 \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
RUN mkdir -p /opt/models \
    && uv run --no-sync python -c "from ultralytics import YOLO; YOLO('/opt/models/yolo11n-pose.pt')"
ENV YOLO_CONFIG_DIR=/tmp/Ultralytics
RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin appuser
COPY --chown=10001:10001 . .
RUN mkdir -p /app/uploads \
    && chown appuser:appuser /app /app/uploads
USER appuser
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--no-access-log"]
