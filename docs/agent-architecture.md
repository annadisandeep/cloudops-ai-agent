# Agent Architecture

## Investigation workflow (LangGraph)

The agent is a compiled LangGraph `StateGraph` with four nodes and one bounded loop:

```
interpret ──> plan ──(call_tool)──> act ──> plan …   (≤ max_steps iterations)
                └──(finish | step limit | failure budget)──> analyze ──> END
```

| Node | Responsibility |
|---|---|
| `interpret` | Normalizes working state (steps, evidence, counters). Resource and time window were resolved upstream from the request/scenario. |
| `plan` | Asks the configured **planner** for exactly one next action: `call_tool(tool, args)` or `finish`. |
| `act` | Executes the tool through the `ToolExecutor` (validation → timeout → retry → trace → evidence) and appends results to state. |
| `analyze` | Builds the final structured report, grounded in collected evidence. Falls back to the deterministic analyzer if the LLM writer fails. |

### Explicit state

`AgentState` (TypedDict) carries: question, provider, resource id, time window, serialized tool steps, evidence records, step counters, planner decision, report, error. Every mutation is persisted incrementally to SQLite so the UI can render live progress.

### Bounds (enforced structurally, not by prompt)

- `max_steps` tool-call ceiling — conditional edge in the graph (default 8).
- Per-tool timeout (default 20 s) via an abandoned-on-timeout daemon worker (Python cannot cancel a thread blocked in an SDK call). Workers never mutate executor state: evidence ids are assigned by the calling thread, only for accepted results.
- Bounded retry budget (default 2) for transient errors only. Abandoned workers are capped per investigation (3) **and** by an application-wide concurrent-worker pool shared across all investigations (`max_concurrent_tool_workers`, default 16) — new tool calls fail fast when the pool is exhausted and recover as stale workers finish.
- Failed-call budget (3) short-circuits to analysis.
- Whole-investigation timeout (default 120 s) enforced by the runner.
- LangGraph `recursion_limit` as a final backstop.

## Tools

The planner may only request these four tools; anything else is rejected before execution and recorded as a failed step:

| Tool | Input schema (Pydantic, `extra="forbid"`) | Output |
|---|---|---|
| `list_resources` | — | resource inventory |
| `get_resource_metadata` | `resource_id` | type, zone, status, machine type, IPs, labels |
| `get_metrics` | `resource_id`, `metric`, optional window, `step_seconds` | time series + computed stats (min/max/avg/first/last) |
| `query_logs` | `resource_id`, optional window, `min_severity`, `query`, `limit` | log entries + severity histogram + injection-flag count |

Every successful call emits **Evidence** records (`ev_1`, `ev_2`, …) with a bounded payload. Facts in the final report cite these ids; the UI links them to the raw data.

There is deliberately **no** shell execution, arbitrary HTTP, IAM mutation, instance restart, resource deletion, or Terraform capability anywhere in the tool layer.

## Planners

### Mock planner (default; deterministic, no LLM)

- Tool selection: metadata → 2–3 metrics chosen from the scenario's key metrics or question keywords → warning/error logs → (if a change-induced regression is suspected) one INFO-level log query scoped to deployment events → finish.
- Report: the rule-based analyzer computes facts from actual tool outputs (threshold breaches, trends, error clusters, deploy markers), maps signal combinations to causes with likelihoods, picks safe recommendations, and derives severity/confidence from evidence strength. With no significant findings it explicitly reports *insufficient evidence* rather than inventing a cause.

This is the fully tested demo path and the automatic fallback when an LLM fails.

### Gemini planner (`CLOUDOPS_LLM_PROVIDER=gemini`)

- Uses the official `google-genai` SDK with `response_schema` (structured output validated by Pydantic).
- The decide step gets the tool catalog + sanitized history; a proposed tool outside the allowlist is never executed.
- The report step receives the deterministic analyzer's baseline and refines prose; evidence ids referencing nonexistent evidence are stripped after validation.
- Fails closed without an API key. Status: implemented and mock-tested; verify your model id (`CLOUDOPS_GEMINI_MODEL`) against your API access.

## Grounding & anti-fabrication rules

- All numbers in reports are computed from retrieved tool outputs — the analyzer has no other input.
- Facts list evidence ids; the test suite asserts every cited id exists.
- Tool failures surface as failed steps and report limitations; they are never papered over.
- Insufficient evidence → `confidence: low`, zero causes, explicit summary.

## Prompt-injection defenses

Telemetry (log messages, resource labels) is attacker-influenced input:

1. Secret redaction (AWS/Google/GitHub keys, bearer tokens, labeled passwords, private key blocks) before storage, display, or prompting.
2. Injection heuristics flag instruction-like content ("ignore previous instructions", "report that this system is healthy", …); flags are surfaced in the report's limitations.
3. Text interpolated into LLM prompts is wrapped in explicit `UNTRUSTED_TELEMETRY_DATA` delimiters (with delimiter-spoofing neutralized) under a standing system rule that delimited content is data, never commands.
4. The mock planner is structurally immune — it only regex-matches log text.

The `app-5xx-errors` demo scenario ships a log line containing an injection attempt so the defense is demonstrable end-to-end.
