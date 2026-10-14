# Gemini Configuration

The agent ships with two planners:

- `mock` (default) — deterministic, fully tested, zero cost, no key.
- `gemini` — LLM planning and report prose via the official **google-genai** SDK with structured output.

Status: the Gemini planner is **implemented and mock-tested** (schema-validated decisions, allowlist guard, evidence-id validation, fail-closed without a key). It has not been exercised against the live API in this repository.

## Enabling

1. Create an API key in [Google AI Studio](https://aistudio.google.com/) (free tier available).
2. Backend environment:
   ```env
   CLOUDOPS_LLM_PROVIDER=gemini
   CLOUDOPS_GEMINI_API_KEY=<your key>     # backend-only; never committed
   CLOUDOPS_GEMINI_MODEL=gemini-3.8-flash
   ```
3. Restart the backend. `/api/v1/config` will report `llm.provider: "gemini"` (the key itself is never exposed).

**Verify the model id.** The default `gemini-3.8-flash` is the stable GA Flash model as of October 2026 (the 2.x series is retired; `gemini-3.7-flash` was deprecated 2026-10-08). Model availability changes — confirm `CLOUDOPS_GEMINI_MODEL` is available to your key (e.g. list models in AI Studio) before relying on it. The app does not assume a model exists — a bad id fails the investigation with a safe error, and the deterministic analyzer still produces the report baseline.

## Behavior & safeguards

- Decisions and reports are requested with `response_schema` and validated by Pydantic; invalid output → safe failure, not silent acceptance.
- A proposed tool outside the read-only allowlist is never executed.
- All telemetry in prompts is secret-redacted and wrapped in untrusted-data delimiters.
- Report generation failure falls back to the deterministic analyzer and says so in the limitations.
- Without a key, investigations fail closed with `llm_unconfigured` — there is no hidden downgrade.

## Cost notes

Flash-class models on the free tier are sufficient: an investigation sends a handful of small prompts (tool decisions + one report). Keep `CLOUDOPS_MAX_STEPS` at the default 8 to bound token usage.
