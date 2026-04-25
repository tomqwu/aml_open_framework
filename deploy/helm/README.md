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
| `dashboard.replicas` | `1` | Dashboard replicas |
| `dashboard.port` | `8501` | Dashboard port |
| `dashboard.spec` | `examples/canadian_schedule_i_bank/aml.yaml` | Spec to load |
| `postgres.enabled` | `true` | Deploy PostgreSQL |
| `postgres.database` | `aml` | Database name |
| `jwt.secret` | `change-me-in-production` | JWT signing secret |
| `ingress.enabled` | `false` | Enable ingress |

## Uninstall

```bash
helm uninstall aml
```
