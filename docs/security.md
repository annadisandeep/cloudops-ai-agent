# Security Architecture

## Threat model (MVP scope)

Single-operator tool, deployed privately (localhost or an access-controlled environment). Primary risks addressed: credential leakage, prompt injection via telemetry, an over-privileged or runaway agent, and unsafe handling of untrusted log content. Multi-tenant isolation is explicitly **out of scope** (see limitations).

## Controls implemented

### Credentials & secrets
- All secrets are backend-only environment variables (`CLOUDOPS_*`); the API never serializes them, and the frontend bundle contains no keys (verified — the client only calls the relative `/api` path).
- GCP uses Application Default Credentials; AWS uses the standard boto3 chain. Nothing is persisted by the app.
- Secret redaction runs on all log content before storage, display, or LLM prompting (AWS key ids, labeled AWS secret keys, Google API keys, bearer tokens, GitHub tokens, labeled passwords, private key blocks).
- `.gitignore` excludes `.env*`, key files, service-account JSON, tfvars, and local databases.

### Cloud access
- **Read-only by construction**: adapters implement only list/get/query operations; no mutating SDK call exists in the codebase.
- **Fail closed**: live providers require an explicit enable flag **and** a non-empty project/account allowlist; AWS additionally verifies the caller identity account against the allowlist via STS before any call. Anything else → 403.
- Demo mode requires no credentials and serves only clearly-labeled synthetic data.
- Bounded pagination, connect/read timeouts, and capped retries on all SDK calls.

### Agent containment
- Tool allowlist of four read-only tools; planner output proposing anything else is rejected and logged.
- Pydantic input validation with `extra="forbid"` on every tool call.
- Step ceiling, per-tool timeout, retry budget, failed-call budget, investigation timeout, LangGraph recursion limit.
- Evidence payloads are size-capped before persistence/prompting.

### Prompt injection
- Injection-pattern detection on telemetry; flagged content is reported in limitations, never obeyed.
- Untrusted-data delimiters (spoof-neutralized) around all telemetry in LLM prompts, with a standing system rule.
- Gemini report output is schema-validated and fabricated evidence ids are stripped; the deterministic analyzer provides the grounded baseline.

### API surface
- CORS restricted to configured origins; only GET/POST; `Content-Type` only.
- Strict request validation (lengths, enums, page bounds, ≤7-day time windows, log limit caps).
- Consistent safe error envelope; unhandled exceptions return a generic 500 and are logged server-side only.
- In-memory sliding-window rate limiting per client IP (general + stricter budget for starting investigations).
- SQLite access uses parameterized queries throughout.
- Frontend container: unprivileged nginx (uid 101, port 8080) with `nosniff`/`DENY`/referrer-policy headers; backend container runs as a dedicated non-root user.

## Known limitations (honest list)

- **No authentication or user isolation.** Demo-mode local use assumes a trusted operator. Any network deployment must sit behind an authenticating proxy (e.g. IAP, ALB+OIDC, Cloudflare Access). This is the documented local-only relaxation.
- **No audit trail** beyond application logs and the investigation history itself.
- Rate limiting is per-process and in-memory — a multi-instance deployment needs a shared limiter (gateway or Redis).
- Secret redaction is pattern-based; unlabeled high-entropy secrets can slip through.
- Injection detection is heuristic; delimiting + allowlisted tools are the primary defense, detection is advisory.
- Live GCP/AWS adapters are mock-tested, not yet exercised against real accounts.
- This project does **not** claim enterprise production readiness: user isolation, audit controls, and access management are future work.

## Reporting

This is a portfolio project; please open a GitHub issue for any security concern.
