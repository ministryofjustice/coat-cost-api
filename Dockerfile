FROM python:3.13-alpine AS builder

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app

FROM python:3.13-alpine

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/app /app/app

RUN apk upgrade --no-cache \
    && apk add --no-cache ca-certificates \
    && adduser -D -s /sbin/nologin -u 1001 appuser \
    && chown -R appuser:appuser /app

ENV PATH="/app/.venv/bin:$PATH"

USER 1001
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
