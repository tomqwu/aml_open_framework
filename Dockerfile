FROM python:3.11-slim

WORKDIR /app

# Install system deps for psycopg2-binary
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ src/
COPY schema/ schema/
COPY examples/ examples/
COPY data/ data/
COPY docs/ docs/
COPY tests/ tests/

RUN pip install --no-cache-dir -e ".[dev,dashboard,api]"

EXPOSE 8000 8501
