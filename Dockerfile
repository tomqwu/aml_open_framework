FROM python:3.11-slim

WORKDIR /app

# Install system deps:
#  - libpq-dev for psycopg2-binary (Postgres driver)
#  - unixodbc-dev for pyodbc (Synapse + Azure SQL driver, [azure] extras)
#  - gcc for compiling native deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev unixodbc-dev gcc && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md dashboard_tenants.example.yaml CHANGELOG.md CONTRIBUTING.md ./
COPY src/ src/
COPY schema/ schema/
COPY examples/ examples/
COPY data/ data/
COPY docs/ docs/
COPY tests/ tests/

RUN pip install --no-cache-dir -e ".[dev,dashboard,api,azure]"

EXPOSE 8000 8501

CMD ["python", "-m", "uvicorn", "aml_framework.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
