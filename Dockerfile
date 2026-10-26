# Build the web UI, then serve it and the API from one Python image.
FROM node:22-slim AS web
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY src/ src/
COPY evals/ evals/
RUN uv sync --locked --no-dev
COPY --from=web /app/web/dist web/dist
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uv run --no-dev uvicorn agentguard.api:app --host 0.0.0.0 --port ${PORT}"]
