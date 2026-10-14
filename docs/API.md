# CloudOps AI Agent — API Contract (v1)

Base URL: `/api/v1` — JSON unless noted. All timestamps are ISO-8601 UTC strings.
Interactive OpenAPI docs are served at `/docs` when the backend is running.

## Conventions

- Every response from demo data includes `"simulated": true` on relevant objects.
- Errors use a consistent envelope:

```json
{ "error": { "code": "not_found", "message": "Investigation inv_x not found" } }
```

HTTP codes: `400` validation, `401/403` auth (live mode), `404` not found, `409` conflict,
`422` request schema violation (FastAPI default, same envelope shape under `detail`), `429` rate limited, `500` safe internal error.

## Endpoints

### GET /api/v1/health
`{ "status": "ok", "version": "0.1.0", "time": "<iso>" }`

### GET /api/v1/config
```json
{
  "demo_mode": true,
  "providers": {
    "demo":  { "enabled": true,  "mode": "demo" },
    "gcp":   { "enabled": false, "mode": "read-only", "allowed_projects": [] },
    "aws":   { "enabled": false, "mode": "read-only", "allowed_accounts": [] }
  },
  "llm": { "provider": "mock", "model": "deterministic-v1" },
  "limits": { "max_steps": 8, "tool_timeout_seconds": 20, "investigation_timeout_seconds": 120 }
}
```
`llm.provider` is `"mock"` or `"gemini"`.

### GET /api/v1/providers
```json
{ "items": [
  { "id": "demo", "name": "Demo Environment", "enabled": true, "mode": "demo",
    "accounts": [ { "id": "demo-project", "name": "Demo Project", "kind": "project" } ] },
  { "id": "gcp", "name": "Google Cloud Platform", "enabled": false, "mode": "read-only", "accounts": [] },
  { "id": "aws", "name": "Amazon Web Services", "enabled": false, "mode": "read-only", "accounts": [] }
] }
```

### GET /api/v1/scenarios
```json
{ "items": [ {
  "id": "gcp-high-cpu",
  "title": "High CPU utilization on GCP VM",
  "provider": "gcp",
  "severity": "high",            // "critical" | "high" | "medium" | "low"
  "category": "performance",     // performance | memory | errors | deployment | storage
  "resource_id": "web-frontend-1",
  "resource_name": "web-frontend-1",
  "description": "...",
  "time_window": { "start": "<iso>", "end": "<iso>" },
  "suggested_question": "Why is my GCP VM experiencing high CPU utilization?",
  "simulated": true
} ] }
```

### GET /api/v1/overview
```json
{
  "resource_counts": { "total": 8, "by_provider": { "gcp": 5, "aws": 3 }, "by_status": { "running": 7, "stopped": 1 } },
  "attention": [ { "resource_id": "web-frontend-1", "provider": "gcp", "reason": "CPU > 90% sustained", "severity": "high", "scenario_id": "gcp-high-cpu" } ],
  "recent_investigations": [ "<InvestigationSummary>" ],
  "simulated": true
}
```

### GET /api/v1/resources
Query: `provider` (required: demo|gcp|aws), `account`, `q` (name/id search), `type`, `status`, `page` (1-based, default 1), `page_size` (default 20, max 100).
```json
{ "items": [ {
  "id": "web-frontend-1", "provider": "gcp", "account": "demo-project",
  "name": "web-frontend-1", "type": "compute-instance",
  "zone": "us-central1-a", "status": "running",
  "machine_type": "e2-standard-2", "internal_ip": "10.0.0.11", "external_ip": null,
  "labels": { "env": "prod", "service": "web" },
  "created_at": "<iso>", "simulated": true
} ], "total": 5, "page": 1, "page_size": 20 }
```

### GET /api/v1/resources/{provider}/{resource_id}
Single resource detail — same object shape, plus `"scenario_ids": ["gcp-high-cpu"]` when demo.

### GET /api/v1/metrics
Query: `provider` (req), `resource_id` (req), `metric` (req), `start`, `end` (iso; default last 1h), `step_seconds` (default 60).
Metric names: `cpu_utilization`, `memory_available_mb`, `disk_used_percent`, `network_in_bytes`, `network_out_bytes`, `http_5xx_count`, `http_request_count`, `latency_ms_p95`.
```json
{ "provider": "gcp", "resource_id": "web-frontend-1", "metric": "cpu_utilization",
  "unit": "percent", "points": [ { "timestamp": "<iso>", "value": 93.4 } ], "simulated": true }
```

### GET /api/v1/logs
Query: `provider` (req), `resource_id` (req), `start`, `end`, `severity` (DEBUG|INFO|WARNING|ERROR|CRITICAL — min level), `q` (substring), `limit` (default 100, max 500).
```json
{ "entries": [ { "timestamp": "<iso>", "severity": "ERROR", "message": "...", "source": "app" } ],
  "total": 42, "simulated": true }
```

### POST /api/v1/investigations
```json
{ "question": "Why is my GCP VM experiencing high CPU utilization?",
  "provider": "demo",
  "scenario_id": "gcp-high-cpu",        // optional — demo incident
  "resource_id": "web-frontend-1",      // optional if scenario_id given
  "time_window": { "start": "<iso>", "end": "<iso>" }   // optional
}
```
→ `201` with the full Investigation object (`status: "running"`). Client polls GET by id.

### GET /api/v1/investigations
Query: `q` (search question/resource), `provider`, `status`, `page`, `page_size`.
`{ "items": [InvestigationSummary], "total": 3, "page": 1, "page_size": 20 }`

InvestigationSummary:
```json
{ "id": "inv_8f3a2c", "question": "...", "provider": "demo", "resource_id": "web-frontend-1",
  "scenario_id": "gcp-high-cpu", "status": "completed", "severity_assessment": "high",
  "created_at": "<iso>", "completed_at": "<iso>", "step_count": 5, "simulated": true }
```

### GET /api/v1/investigations/{id}
Full Investigation:
```json
{
  "id": "inv_8f3a2c", "question": "...", "provider": "demo",
  "resource_id": "web-frontend-1", "scenario_id": "gcp-high-cpu",
  "status": "running",   // queued | running | completed | failed
  "created_at": "<iso>", "completed_at": null,
  "time_window": { "start": "<iso>", "end": "<iso>" },
  "steps": [ {
    "index": 0, "tool": "get_metrics", "status": "completed",  // running | completed | failed
    "input": { "resource_id": "web-frontend-1", "metric": "cpu_utilization" },
    "output_summary": "60 points; min 12.1%, max 96.8%, last 94.2%",
    "started_at": "<iso>", "duration_ms": 12, "evidence_ids": ["ev_1"], "error": null
  } ],
  "evidence": [ {
    "id": "ev_1", "type": "metric",   // metric | log | metadata
    "source_tool": "get_metrics", "title": "cpu_utilization for web-frontend-1",
    "summary": "CPU sustained above 90% from 14:05 to 14:40 UTC",
    "data": { "...": "tool output payload (bounded)" }, "simulated": true
  } ],
  "report": null,        // present when completed — see Report
  "error": null
}
```

Report:
```json
{
  "summary": "one-paragraph assessment",
  "severity_assessment": "high",
  "observed_facts": [ { "statement": "...", "evidence_ids": ["ev_1"] } ],
  "possible_causes": [ { "cause": "...", "likelihood": "likely|possible|unlikely", "rationale": "...", "evidence_ids": ["ev_2"] } ],
  "recommendations": [ { "action": "...", "risk": "low|medium|high", "rationale": "..." } ],
  "confidence": "high|medium|low",
  "limitations": [ "..." ],
  "llm_provider": "mock"
}
```

### GET /api/v1/investigations/{id}/report.md
`text/markdown` download of the full incident report. 404 if not completed.

## Frontend integration notes

- Dev server proxies `/api` → `http://localhost:8000` (Vite proxy).
- Poll running investigations every 1000 ms until `status` ∈ {completed, failed}.
- Render `simulated: true` data with a visible "Simulated data" badge.
