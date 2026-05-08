# Helm Deployment

Deploy the AML Open Framework on Kubernetes.

## Prerequisites

- Kubernetes 1.24+
- Helm 3.x
- Container image built and pushed to a registry

## Build the image

```bash
docker build -t your-registry/aml-framework:latest .
docker push your-registry/aml-framework:latest
```

## Install

```bash
helm install aml ./deploy/helm/ \
  --set image.repository=your-registry/aml-framework \
  --set jwt.secret=$(openssl rand -hex 32)
```

## Configuration

See `values.yaml` for all configurable options:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `image.repository` | `aml-framework` | Container image |
| `image.tag` | `latest` | Image tag |
| `api.replicas` | `1` | API server replicas |
| `api.port` | `8000` | API port |
| `api.dataRoots` | `data` | API local data source roots |
| `api.uploadRoot` | `data/uploads` | API upload storage root |
| `api.artifactRoot` | `data/api-artifacts` | API run artifact storage root |
| `api.maxUploadBytes` | `26214400` | Max size for each uploaded CSV file |
| `api.allowRemoteDataSources` | `false` | Enable API S3/GCS/Snowflake/BigQuery sources |
| `dashboard.replicas` | `1` | Dashboard replicas |
| `dashboard.port` | `8501` | Dashboard port |
| `dashboard.spec` | `examples/canadian_schedule_i_bank/aml.yaml` | Spec to load |
| `postgres.enabled` | `true` | Deploy PostgreSQL |
| `postgres.database` | `aml` | Database name |
| `database.url` | `""` | External Postgres URL when `postgres.enabled=false` |
| `cosmos.enabled` | `false` | Use Azure Cosmos DB instead of Postgres. When `true`, `COSMOS_ENDPOINT` + `COSMOS_DATABASE` are wired into both API and dashboard pods and the Python persistence layer selects Cosmos. Pair with `azure.workloadIdentityClientId` + a Cosmos Data Contributor role assignment. |
| `cosmos.endpoint` | `""` | Cosmos account endpoint. Required when `cosmos.enabled=true`. |
| `cosmos.database` | `aml` | Cosmos database name. |
| `jwt.secret` | `replace-with-32-plus-byte-random-secret` | JWT signing secret (32+ bytes) |
| `oidc.issuerUrl` | `""` | OIDC issuer URL |
| `oidc.audience` | `""` | OIDC audience; required when `oidc.issuerUrl` is set |
| `oidc.roleClaim` | `roles` | OIDC role claim path |
| `oidc.tenantClaim` | `tid` | OIDC tenant claim path |
| `oidc.allowedTenants` | `""` | Comma-separated allowed OIDC tenants |
| `ingress.enabled` | `false` | Enable ingress |

## Uninstall

```bash
helm uninstall aml
```
