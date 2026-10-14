# Testing Guide

## Backend (pytest — 112 tests)

```powershell
cd backend
.\.venv\Scripts\python -m pytest tests -q        # full suite (~16 s)
.\.venv\Scripts\python -m ruff check app tests   # lint
```

| Area | File | Covers |
|---|---|---|
| Demo fixtures | `test_demo_data.py` | determinism, anomaly presence, healthy baselines, severity/limit/query filters, scenario-resource integrity |
| Providers | `test_providers.py` | demo adapter filtering/labeling/404s; registry fail-closed matrix (demo off, provider off, empty allowlist, non-allowlisted project/account); GCP instance mapping + metric map via mocked clients; AWS pagination/mapping/metric sorting via mocked boto3; STS allowlist rejection |
| Security | `test_security.py` | secret redaction patterns, injection detection, delimiter spoofing, length bounds, rate limiter window math |
| Tools | `test_tools.py` | allowlist rejection, schema violations (incl. `extra` args), not-found no-retry, evidence generation, injection flagging, demo-secret redaction in evidence, timeout, transient-retry, payload bounding |
| Agent graph | `test_agent_graph.py` | full run grounding (every fact cites real evidence), step-limit enforcement, resource resolution from inventory, insufficient-evidence/no-answer path, failed-call budget, planner-crash fallback, disallowed-tool containment, scenario metric routing |
| Planners | `test_planner.py` | keyword metric routing; Gemini fail-closed without key, disallowed-tool guard, fabricated-evidence-id stripping |
| Persistence & reports | `test_db_and_report.py` | SQLite roundtrip, upsert, search filters, Markdown sections, failed-report rendering |
| API | `test_api.py` | every endpoint; validation errors; error envelope; pagination/search; log redaction; full investigation lifecycle incl. export; restart persistence; live-mode 403; Gemini-missing-key failure; per-IP investigation rate limit; injection-flag surfacing; all 6 scenarios complete with causes |
| Real HTTP e2e | `test_e2e_http.py` | uvicorn on a real socket → create → poll → completed report → Markdown export |

Gemini and the cloud SDKs are **mocked everywhere** — CI needs no credentials and demo mode is the only live path exercised.

## Frontend (vitest — 23 tests)

```powershell
cd frontend
npm test -- --run
npm run lint
npm run build
```

Covers: badge variants, SVG metric chart (data/empty/single point), API client error envelope → typed `ApiError`, investigation detail rendering + polling stop, resources search refetch, history empty state. All fetches mocked.

## CI

`.github/workflows/ci.yml` runs on push/PR: backend lint+tests, frontend lint+tests+build, both Docker image builds, and `terraform fmt -check` + `validate` (no credentials, nothing provisioned).
