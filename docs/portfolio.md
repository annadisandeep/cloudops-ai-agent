# Portfolio Project Description

## CloudOps AI Agent — evidence-grounded incident investigation for cloud infrastructure

**One-liner:** An AI agent that investigates cloud incidents the way a good SRE does — pull the metrics, read the logs, correlate, and write up findings with citations — built with LangGraph, FastAPI, React/TypeScript, and read-only GCP/AWS adapters.

### The problem it demonstrates

LLM products in operations fail in two predictable ways: they hallucinate root causes, and they get handed too much power. This project is an exercise in building the opposite: an agent that is **useful because it is constrained** — four read-only tools, hard step/timeout budgets, schema-validated inputs and outputs, and a reporting layer where every stated fact must cite an evidence record produced by a real tool call.

### What I built

- **Agent engine** — a LangGraph state machine (interpret → plan → act loop → analyze) with explicit state, a tool allowlist, bounded retries/timeouts, and incremental persistence so the UI streams the investigation live. Two interchangeable planners: a deterministic rule-based one (zero-cost demo + fallback) and a Gemini planner using `google-genai` structured output.
- **Evidence discipline** — tool calls emit typed Evidence records; the analyzer computes facts (threshold breaches, trends, error clusters, deploy markers) strictly from those payloads; causes carry likelihoods and rationale; reports state confidence and limitations, including an explicit insufficient-evidence path. Tests assert every cited evidence id exists.
- **Security engineering** — fail-closed provider allowlists (STS-verified on AWS), secret redaction on all telemetry, prompt-injection detection + untrusted-data delimiting (with a demo scenario that actually attempts an injection), rate limiting, strict validation, non-root containers, no credentials anywhere near the browser.
- **Cloud adapters** — read-only GCP (Compute/Monitoring/Logging) and AWS (EC2/CloudWatch/Logs) adapters with pagination, bounded retries, and metric mapping; a deterministic synthetic demo environment with six realistic incident scenarios so the entire product runs with zero credentials.
- **Product surface** — a minimal monochrome React dashboard (Linear/Vercel-style): inventory, monitoring charts (hand-rolled SVG), an investigation workspace with a tool-execution timeline and evidence panel, persistent incident history, and Markdown report export.
- **Delivery** — 153 backend + 23 frontend tests (including a real-HTTP end-to-end investigation), GitHub Actions CI, non-root Docker images + Compose, and validation-ready Terraform (Cloud Run + least-privilege IAM) that provisions nothing by default.

### Honest status

Demo mode is fully implemented and tested. The Gemini planner is implemented, mock-tested, and has been verified end-to-end against the live Gemini API (`gemini-3.5-flash-lite`, 2026-10-14) on simulated telemetry, including the resilient fallback path after a real `503`. GCP/AWS live adapters are implemented and mock-tested, pending verification against real cloud accounts. There is no multi-user auth — deployment guidance mandates an authenticating proxy.

---

## Suggested LinkedIn description

> **CloudOps AI Agent** — an open-source platform that investigates cloud infrastructure incidents with evidence, not guesses.
>
> A LangGraph-orchestrated agent interprets an incident question, chooses from a strict allowlist of read-only tools, pulls monitoring metrics, logs, and metadata from GCP/AWS (or a built-in simulated environment), correlates the signals, and produces a structured report where every fact cites the evidence behind it — complete with likelihood-ranked causes, safe remediation steps, confidence, and limitations.
>
> Built with Python/FastAPI, LangGraph, Gemini (structured output, verified against the live API), React + TypeScript, Docker, GitHub Actions, and Terraform. Security-first design: fail-closed cloud allowlists, secret redaction, prompt-injection defenses for untrusted logs, bounded agent execution, and zero credentials in the browser. 176 automated tests including a real-HTTP end-to-end agent run.
>
> #AgenticAI #LangGraph #CloudOps #SRE #GCP #AWS #FastAPI #React #Terraform
