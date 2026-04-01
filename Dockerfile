FROM python:3.12-slim AS base
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock README.md ./
ARG SETUPTOOLS_SCM_PRETEND_VERSION=0.0.0
ENV SETUPTOOLS_SCM_PRETEND_VERSION=${SETUPTOOLS_SCM_PRETEND_VERSION}
RUN mkdir -p src/hyperweave
RUN uv sync --no-dev --frozen
COPY src/ src/
EXPOSE 8080
CMD ["uv", "run", "uvicorn", "hyperweave.serve.app:app", "--host", "0.0.0.0", "--port", "8080"]
