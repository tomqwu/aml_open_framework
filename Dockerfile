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

# `setuptools-scm` derives the package version from git tags, but the
# image doesn't carry `.git/`. The acr-build wrapper passes the
# already-resolved version via `--build-arg APP_VERSION=$(git describe
# --tags --always --dirty)`; setuptools-scm honors the project-scoped
# pretend-version env. Default `0.1.0+local` keeps non-CI `docker build`
# from blowing up.
ARG APP_VERSION=0.1.0+local
ENV SETUPTOOLS_SCM_PRETEND_VERSION_FOR_AML_OPEN_FRAMEWORK=$APP_VERSION

RUN pip install --no-cache-dir -e ".[dev,dashboard,api,azure]"

# Capture the git SHA the image was built from so the running container
# can self-identify in /api/v1/health + the dashboard topbar. Set with
# `docker build --build-arg GIT_SHA=$(git rev-parse --short HEAD)`; the
# Azure deploy (and the `az acr build` invocation) pass it explicitly.
# Defaults to "dev" for local `docker build` without the flag.
ARG GIT_SHA=dev
ENV AML_BUILD_SHA=$GIT_SHA

EXPOSE 8000 8501

CMD ["python", "-m", "uvicorn", "aml_framework.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
