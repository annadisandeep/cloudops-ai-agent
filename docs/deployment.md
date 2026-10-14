# Deployment Guide

> Nothing in this repo provisions or deploys anything automatically. Terraform stacks default to disabled, and no deployment workflow runs from CI.

## Local (recommended for the demo)

```bash
docker compose up --build      # http://localhost:8080
```

- `backend`: python:3.12-slim, non-root user, health-checked `/api/v1/health`, SQLite persisted in the `cloudops-data` volume.
- `frontend`: static build on unprivileged nginx (uid 101, port 8080) proxying `/api/` to the backend service — same-origin, no exposed backend port.

## Secret management

- Local: `.env` files (gitignored), or compose `env_file`. Never commit keys; `backend/.env.example` documents every variable.
- Cloud: use the platform secret store (GCP Secret Manager / AWS Secrets Manager / SSM) and inject as env vars at runtime. The Terraform intentionally contains no secret values; wire `CLOUDOPS_GEMINI_API_KEY` from Secret Manager, never tfvars.
- If any deployment is internet-reachable, put an authenticating proxy in front (IAP / ALB+OIDC / Cloudflare Access) — the MVP has no built-in auth (see [security.md](security.md)).

## Terraform (validation-ready)

```bash
cd infrastructure/terraform
terraform init -backend=false
terraform validate              # passes with zero credentials
```

What it defines (all behind `enable_gcp` / `enable_aws`, default **false**):

- **GCP**: Artifact Registry repo; `cloudops-backend` Cloud Run service (non-public ingress, scale-to-zero, 512 Mi, health-probed) running as a dedicated service account holding only `monitoring.viewer`, `logging.viewer`, `compute.viewer`; `cloudops-frontend` Cloud Run service.
- **AWS**: the least-privilege read-only IAM policy + assumable role for the agent (no compute).

To actually deploy (requires owner approval):

```bash
# 1. Build & push images
gcloud auth configure-docker us-central1-docker.pkg.dev
docker build -t us-central1-docker.pkg.dev/<project>/cloudops/backend:v1 ./backend
docker push us-central1-docker.pkg.dev/<project>/cloudops/backend:v1
# (same for frontend)

# 2. Review the plan — nothing applies without your explicit approval
cp terraform.tfvars.example terraform.tfvars   # edit; set enable_gcp = true
terraform plan
terraform apply                                 # manual, deliberate
```

Note: the backend service is created before the registry contains images on a first pass — push images first, or apply the registry alone with `-target`.

## Logging & health

- Structured app logs to stdout (picked up by Cloud Run/Docker logging).
- Health endpoints: `/api/v1/health` (backend), `/` (frontend). Both containers define Docker `HEALTHCHECK`s; Cloud Run uses a startup probe on the backend.

## Cost considerations

| Component | Expected cost |
|---|---|
| Demo mode locally | $0 |
| Cloud Run (scale-to-zero, 2 small services, light use) | ~$0–5/month |
| Artifact Registry | pennies at this image size |
| Cloud Monitoring/Logging **reads** | free-tier API calls for this volume |
| Gemini (flash model, bounded steps) | free tier typically sufficient |
| AWS | IAM is free; CloudWatch `GetMetricStatistics` reads are ~$0.01/1k requests |

Keep `min_instance_count = 0` and the demo scenario volume and you stay at effectively zero idle cost.
