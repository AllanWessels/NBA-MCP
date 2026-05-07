FROM python:3.12-slim

WORKDIR /app

# uv handles dependency install + venv. Copy lockfile first for layer caching.
RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
COPY uv.lock* ./
RUN uv sync --no-dev || uv sync

COPY src/ ./src/

EXPOSE 8000

CMD ["uv", "run", "python", "-m", "src.server"]
