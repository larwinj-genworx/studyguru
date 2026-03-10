# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

# 1. Install uv by copying it from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 2. Add uv-specific environment variables for better performance
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Use --system if you want to install directly into the image instead of a venv.
COPY requirements.txt ./
RUN uv pip install --system -r requirements.txt

COPY src ./src
COPY Temp ./Temp

ENV PYTHONPATH=/app
EXPOSE 8000

# 4. Use 'uv run' to execute your application
CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
