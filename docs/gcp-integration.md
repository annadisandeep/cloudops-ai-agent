# GCP Read-Only Integration

Status: **implemented and mock-tested** — not yet verified against a live project. Demo mode emulates GCP-shaped resources without any of this setup.

## What the adapter uses

| Capability | API | Call |
|---|---|---|
| Inventory | Compute Engine | `instances.aggregatedList` (paginated, bounded) |
| Metrics | Cloud Monitoring | `projects.timeSeries.list` (ALIGN_MEAN) |
| Logs | Cloud Logging | `entries.list` with a bounded, parameter-built filter |

Metric mapping: `cpu_utilization`, `network_in_bytes`, `network_out_bytes` come from built-in Compute metrics. `memory_available_mb` and `disk_used_percent` require the **Ops Agent** on the VM (`agent.googleapis.com/…`); without it those series return empty.

## Setup

1. Create (or pick) a project and enable APIs:
   ```bash
   gcloud services enable compute.googleapis.com monitoring.googleapis.com logging.googleapis.com
   ```
2. Give the identity running the backend read-only roles only:
   - `roles/compute.viewer`
   - `roles/monitoring.viewer`
   - `roles/logging.viewer`
3. Provide Application Default Credentials on the **server**:
   ```bash
   gcloud auth application-default login          # local dev
   # or attach a service account with the roles above in Cloud Run/GCE
   ```
4. Configure and restart the backend:
   ```env
   CLOUDOPS_GCP_ENABLED=true
   CLOUDOPS_GCP_ALLOWED_PROJECTS=my-project-id
   ```

The allowlist is mandatory — with `CLOUDOPS_GCP_ENABLED=true` and an empty allowlist every GCP request fails closed (403). Requests for a project outside the list are rejected. The app never enumerates all projects your credentials can see; only allowlisted projects are touched.

## Verification checklist (when you have a real project)

```powershell
# resources
curl "http://localhost:8000/api/v1/resources?provider=gcp"
# metrics for one instance
curl "http://localhost:8000/api/v1/metrics?provider=gcp&resource_id=<instance-name>&metric=cpu_utilization"
```

Update the README feature table from "mock-tested" to "live-verified" once this passes.
