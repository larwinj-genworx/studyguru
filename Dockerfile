# syntax=docker/dockerfile:1
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.10.8 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY requirements.txt ./
RUN uv venv "$VIRTUAL_ENV" \
    && uv pip install --python "$VIRTUAL_ENV/bin/python" -r requirements.txt

COPY .env ./.env
COPY src ./src
COPY Temp ./Temp

EXPOSE 8000

CMD ["sh", "-c", "uv run --active uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
