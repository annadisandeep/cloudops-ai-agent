# Gemini Configuration

The agent ships with two planners:

- `mock` (default) — deterministic, fully tested, zero cost, no key.
- `gemini` — LLM planning and report prose via the official **google-genai** SDK with structured output.

Status: the Gemini planner is **implemented, mock-tested, and verified against the live Gemini API**. Automated tests cover schema-validated decisions, the allowlist guard, evidence-id validation, fail-closed behaviour without a key, and the resilient fallback. On 2026-10-14 it was run manually with `CLOUDOPS_GEMINI_MODEL=gemini-3.5-flash-lite` on simulated demo telemetry: two investigations completed with Gemini-chosen tool calls and Gemini-authored reports (`llm_provider: "gemini"`, 4 and 1 tool calls, ~10 s and ~6 s). An earlier run with `gemini-3.8-flash` hit a live `503 UNAVAILABLE` at planning step 0 and completed via the deterministic fallback with an `api_server_error` limitation. The verified run also surfaced that the model guessed `start_time`/`end_time` for the `start`/`end` arguments; the prompt now carries exact schema-derived signatures (see [agent-architecture.md](agent-architecture.md)). Live cloud telemetry was **not** involved in any of these runs.

## Enabling

1. Create an API key in [Google AI Studio](https://aistudio.google.com/) (free tier available).
2. Backend environment:
   ```env
   CLOUDOPS_LLM_PROVIDER=gemini
   CLOUDOPS_GEMINI_API_KEY=<your key>     # backend-only; never committed
   CLOUDOPS_GEMINI_MODEL=gemini-3.8-flash
   ```
3. Restart the backend. `/api/v1/config` will report `llm.provider: "gemini"` (the key itself is never exposed).

**Verify the model id.** The default `gemini-3.8-flash` is the stable GA Flash model as of October 2026 (the 2.x series is retired; `gemini-3.7-flash` was deprecated 2026-10-08). The id verified end-to-end in this repository is `gemini-3.5-flash-lite`, chosen because `gemini-3.8-flash` was returning `503 UNAVAILABLE` under demand at the time. Model availability changes — confirm `CLOUDOPS_GEMINI_MODEL` is available to your key (e.g. list models in AI Studio) before relying on it. The app does not assume a model exists — a bad id fails the investigation with a safe error, and the deterministic analyzer still produces the report baseline.

## Behavior & safeguards

- Decisions and reports are requested with `response_schema` and validated by Pydantic; invalid output → safe failure, not silent acceptance. Tool arguments travel as a JSON string (`args_json`) because the Gemini Developer API rejects open-dict schemas (`additionalProperties`); they are parsed and schema-validated locally before any tool sees them.
- A proposed tool outside the read-only allowlist is never executed.
- All telemetry in prompts is secret-redacted and wrapped in untrusted-data delimiters.
- **Resilient fallback**: a runtime Gemini failure (API 5xx, quota, unavailable model, invalid request, malformed structured output, network) degrades that investigation to the deterministic planner — evidence collection continues under all existing limits instead of ending early. The failure is logged and surfaced in the report's limitations with a sanitized category (`model_unavailable`, `quota_exhausted`, `invalid_request`, `api_server_error`, `auth_error`, `malformed_structured_output`, `transient_network`), and the report's `llm_provider` always names the engine that actually wrote it — a fallback report is never attributed to Gemini.
- Without a key, investigations fail closed with `llm_unconfigured` — misconfiguration is not silently downgraded.

## Cost notes

Flash-class models on the free tier are sufficient: an investigation sends a handful of small prompts (tool decisions + one report). Keep `CLOUDOPS_MAX_STEPS` at the default 8 to bound token usage.
