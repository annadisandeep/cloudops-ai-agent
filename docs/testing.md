# Testing Guide

## Backend (pytest — 153 tests)

```powershell
cd backend
.\.venv\Scripts\python -m pytest tests -q        # full suite (~25 s)
.\.venv\Scripts\python -m ruff check app tests   # lint
```

| Area | File | Covers |
|---|---|---|
| Demo fixtures (7) | `test_demo_data.py` | determinism, anomaly presence, healthy baselines, severity/limit/query filters, scenario-resource integrity |
| Providers (25) | `test_providers.py` | demo adapter filtering/labeling/404s; registry fail-closed matrix (demo off, provider off, empty allowlist, non-allowlisted project/account); GCP instance mapping + metric map via mocked clients; AWS pagination/mapping/metric sorting via mocked boto3; STS allowlist rejection |
| Security (18) | `test_security.py` | secret redaction patterns, injection detection, delimiter spoofing, length bounds, rate limiter window math |
| Tools (15) | `test_tools.py` | allowlist rejection, schema violations (incl. `extra` args), not-found no-retry, evidence generation, injection flagging, demo-secret redaction in evidence, timeout, transient-retry, payload bounding |
| Agent graph (8) | `test_agent_graph.py` | full run grounding (every fact cites real evidence), step-limit enforcement, resource resolution from inventory, insufficient-evidence/no-answer path, failed-call budget, planner-crash fallback, disallowed-tool containment, scenario metric routing |
| Planners (7) | `test_planner.py` | keyword metric routing; Gemini fail-closed without key, disallowed-tool guard, fabricated-evidence-id stripping |
| Resilient fallback (17) | `test_resilient_planner.py` | Gemini failure before the first tool call, mid-stream failure continuation, report-writer failure, honest `llm_provider` attribution for both engines, secret redaction in limitations and logs, error-category matrix, `args_json` parsing (valid / malformed / non-object) |
| Gemini tool arguments (7) | `test_gemini_tool_args.py` | schema-derived argument signatures in the planning prompt; the live-observed `start_time`/`end_time` mistakes rejected with field-naming guidance; corrected `start`/`end` calls succeed; mixed valid+unknown fields reject the whole call; persistent bad-args planner bounded by the failed-call budget with a report still produced |
| Configuration (7) | `test_config.py` | default model id, env override, model label, `/config` reflects overrides, Gemini API key never leaks from any endpoint or log |
| Persistence & reports (5) | `test_db_and_report.py` | SQLite roundtrip, upsert, search filters, Markdown sections, failed-report rendering |
| API (36) | `test_api.py` | every endpoint; validation errors; error envelope; pagination/search; log redaction; full investigation lifecycle incl. export; restart persistence; live-mode 403; Gemini-missing-key failure; per-IP investigation rate limit; injection-flag surfacing; all 6 scenarios complete with causes |
| Real HTTP e2e (1) | `test_e2e_http.py` | uvicorn on a real socket → create → poll → completed report → Markdown export |

Gemini and the cloud SDKs are **mocked everywhere** — CI needs no credentials and demo mode is the only live path exercised. The session fixture chdirs into a temp directory and resets the `CLOUDOPS_*` LLM variables, so a developer's local `backend/.env` (real key, model overrides) can never influence or leak into tests.

The Gemini planner was additionally exercised **manually** against the live API with `gemini-3.5-flash-lite` on 2026-10-14 (two completed Gemini-authored investigations on simulated telemetry, plus one verified fallback after a live `503`). That manual run is documented in the README and [gemini.md](gemini.md); it is not part of the automated suite.

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
