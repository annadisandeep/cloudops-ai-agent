"""Agent tool layer.

Every tool is:
- read-only (inventory, metrics, logs, metadata — nothing else exists);
- allowlisted by name (the planner cannot invent tools);
- schema-validated on input (Pydantic) before execution;
- bounded (timeout per call, retry budget, output payload cap);
- traced (each execution produces a ToolStep and Evidence records).

There is deliberately no shell, HTTP, IAM, restart, delete, or apply tool.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from ..config import get_settings
from ..errors import ApiError
from ..providers.base import ProviderAdapter
from ..schemas import Evidence, TimeWindow, ToolStep
from .sanitize import detect_injection, sanitize_untrusted

ALLOWED_TOOLS = frozenset({"list_resources", "get_resource_metadata", "get_metrics", "query_logs"})


class ToolTimeout(Exception):
    """A tool call exceeded its wall-clock budget; its worker was abandoned."""


class WorkerBudgetExhausted(Exception):
    """Too many abandoned (timed-out) workers; refusing to start more."""


TRANSIENT_ERRORS = (ConnectionError, TimeoutError)

# Hard cap on worker threads a single investigation may abandon via timeouts.
# Python cannot cancel a thread blocked inside an SDK call, so a timed-out
# worker keeps running (as a daemon) until the underlying call returns on its
# own; this cap keeps that leakage strictly bounded per investigation.
MAX_ABANDONED_WORKERS = 3

# Placeholder id carried by Evidence while it is still inside a worker thread.
# Final ids are assigned ONLY by the calling thread (see
# ToolExecutor._assign_evidence_ids) so an abandoned worker can never race the
# id counter or leak a numbered Evidence record.
PENDING_EVIDENCE_ID = "ev_pending"


class _WorkerSlots:
    """Application-wide bound on concurrently running tool worker threads.

    Every tool worker (including ones later abandoned by a timeout) holds a
    slot from spawn until its underlying call actually returns — so the total
    number of live tool threads across ALL concurrent investigations is capped
    by ``max_concurrent_tool_workers``. When the pool is exhausted, new tool
    calls fail fast instead of spawning unbounded threads.

    Releases are matched to acquisitions with a generation token so the
    test-only ``reset()`` cannot be double-decremented by stale workers
    releasing after a reset.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = 0
        self._generation = 0

    def _limit(self) -> int:
        return get_settings().max_concurrent_tool_workers

    def try_acquire(self) -> int | None:
        """Returns a release token, or None when the pool is exhausted."""
        with self._lock:
            if self._active >= self._limit():
                return None
            self._active += 1
            return self._generation

    def release(self, token: int) -> None:
        with self._lock:
            if token == self._generation and self._active > 0:
                self._active -= 1

    def active(self) -> int:
        with self._lock:
            return self._active

    def reset(self) -> None:
        """Test helper: invalidate outstanding tokens and zero the count."""
        with self._lock:
            self._generation += 1
            self._active = 0


WORKER_SLOTS = _WorkerSlots()


class ListResourcesInput(BaseModel):
    model_config = {"extra": "forbid"}


class GetResourceMetadataInput(BaseModel):
    model_config = {"extra": "forbid"}
    resource_id: str = Field(min_length=1, max_length=200)


class GetMetricsInput(BaseModel):
    model_config = {"extra": "forbid"}
    resource_id: str = Field(min_length=1, max_length=200)
    metric: str = Field(min_length=1, max_length=100)
    start: datetime | None = None
    end: datetime | None = None
    step_seconds: int = Field(default=60, ge=15, le=3600)


class QueryLogsInput(BaseModel):
    model_config = {"extra": "forbid"}
    resource_id: str = Field(min_length=1, max_length=200)
    start: datetime | None = None
    end: datetime | None = None
    min_severity: str = Field(default="WARNING", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    query: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=100, ge=1, le=500)


TOOL_SCHEMAS: dict[str, type[BaseModel]] = {
    "list_resources": ListResourcesInput,
    "get_resource_metadata": GetResourceMetadataInput,
    "get_metrics": GetMetricsInput,
    "query_logs": QueryLogsInput,
}

TOOL_DESCRIPTIONS: dict[str, str] = {
    "list_resources": "List cloud resources visible to the selected provider/account. No arguments.",
    "get_resource_metadata": (
        "Fetch metadata for one resource (type, zone, status, labels, IPs). "
        "Arguments: resource_id."
    ),
    "get_metrics": (
        "Fetch a metric time series for a resource. "
        "Arguments: resource_id, metric, start, end, step_seconds. "
        "Metrics: cpu_utilization, memory_available_mb, disk_used_percent, network_in_bytes, "
        "network_out_bytes, http_5xx_count, http_request_count, latency_ms_p95. "
        "Time bounds are named exactly 'start' and 'end' (ISO-8601); omit them to use the "
        "investigation window."
    ),
    "query_logs": (
        "Query log entries for a resource, filtered by minimum severity. "
        "Arguments: resource_id, start, end, min_severity, query, limit. "
        "Time bounds are named exactly 'start' and 'end' (ISO-8601); omit them to use the "
        "investigation window."
    ),
}


def tool_argument_spec() -> str:
    """Exact per-tool argument signatures, generated from the Pydantic input
    schemas (single source of truth — cannot drift from validation)."""
    lines = []
    for name in sorted(ALLOWED_TOOLS):
        fields = []
        for fname, finfo in TOOL_SCHEMAS[name].model_fields.items():
            kind = "required" if finfo.is_required() else "optional"
            fields.append(f"{fname} ({kind})")
        lines.append(f"- {name}({', '.join(fields) if fields else 'no arguments'})")
    return "\n".join(lines)


def summarize_series(points: list[tuple[datetime, float]], unit: str) -> dict[str, Any]:
    if not points:
        return {"count": 0}
    values = [v for _, v in points]
    first_ts, last_ts = points[0][0], points[-1][0]
    return {
        "count": len(values),
        "unit": unit,
        "min": round(min(values), 2),
        "max": round(max(values), 2),
        "avg": round(sum(values) / len(values), 2),
        "first": round(values[0], 2),
        "last": round(values[-1], 2),
        "start": first_ts.isoformat(),
        "end": last_ts.isoformat(),
    }


class ToolExecutor:
    """Executes allowlisted tools against one provider adapter, with trace."""

    def __init__(
        self,
        adapter: ProviderAdapter,
        time_window: TimeWindow,
        investigation_id: str,
    ) -> None:
        self.adapter = adapter
        self.window = time_window
        self.investigation_id = investigation_id
        self.settings = get_settings()
        self._evidence_counter = 0
        self._abandoned_workers = 0

    def _next_evidence_id(self) -> str:
        # CALLER-THREAD ONLY: never invoked from a worker thread (see
        # _assign_evidence_ids), so abandoned workers cannot race this counter.
        self._evidence_counter += 1
        return f"ev_{self._evidence_counter}"

    def _assign_evidence_ids(self, evidence: list[Evidence]) -> None:
        """Replace placeholder ids with final sequential ids.

        Runs in the calling thread, strictly after a successful (non-timed-out)
        worker return. Evidence built inside an abandoned worker keeps its
        PENDING placeholder and is discarded with the worker's outcome, so ids
        are unique and gapless regardless of when stale workers finish.
        """
        for ev in evidence:
            ev.id = self._next_evidence_id()

    # -- execution ----------------------------------------------------------

    def execute(self, tool: str, raw_args: dict[str, Any], step_index: int) -> tuple[ToolStep, list[Evidence]]:
        started = datetime.now(UTC)
        step = ToolStep(
            index=step_index, tool=tool, status="running", input=raw_args, started_at=started
        )

        if tool not in ALLOWED_TOOLS:
            step.status = "failed"
            step.error = f"Tool '{tool}' is not in the allowlist."
            step.duration_ms = 0
            return step, []

        try:
            args = TOOL_SCHEMAS[tool](**raw_args)
        except ValidationError as exc:
            # Never silently discard unknown arguments: the call is rejected and
            # the error names the offending fields plus the exact allowed set, so
            # an LLM planner can self-correct on its next decision (the error
            # text flows back into its prompt history).
            unexpected = sorted({
                str(e["loc"][0]) for e in exc.errors() if e["type"] == "extra_forbidden" and e.get("loc")
            })
            parts = []
            if unexpected:
                parts.append(f"unexpected field(s): {', '.join(unexpected)}")
            parts.extend(
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
                for e in exc.errors() if e["type"] != "extra_forbidden"
            )
            allowed = ", ".join(TOOL_SCHEMAS[tool].model_fields.keys()) or "none"
            step.status = "failed"
            step.error = (
                f"Invalid tool arguments ({'; '.join(parts[:4])}). "
                f"Allowed fields for {tool}: {allowed}."
            )
            step.duration_ms = 0
            return step, []
        step.input = json.loads(args.model_dump_json(exclude_none=True))

        attempts = 0
        last_error: str | None = None
        while attempts <= self.settings.tool_retry_budget:
            attempts += 1
            try:
                output, summary, evidence = self._run_with_timeout(tool, args)
                # Ids are assigned here, in the caller thread, only for results
                # that were actually accepted (never inside workers).
                self._assign_evidence_ids(evidence)
                step.status = "completed"
                step.output_summary = summary
                step.duration_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
                step.evidence_ids = [e.id for e in evidence]
                return step, evidence
            except ToolTimeout:
                # Retryable, but each timeout consumes abandoned-worker budget.
                last_error = f"Tool timed out after {self.settings.tool_timeout_seconds}s"
            except WorkerBudgetExhausted as exc:
                last_error = str(exc) or "Tool worker budget exhausted."
                break
            except ApiError as exc:
                # Deterministic failures (not found, validation) are not retried.
                last_error = exc.message
                break
            except TRANSIENT_ERRORS as exc:
                last_error = f"Transient error: {type(exc).__name__}"
                time.sleep(min(0.2 * attempts, 1.0))
            except Exception as exc:  # safe catch-all; never crash the graph
                last_error = f"Tool error: {type(exc).__name__}"
                break

        step.status = "failed"
        step.error = last_error or "Unknown tool failure"
        step.duration_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
        return step, []

    def _run_with_timeout(self, tool: str, args: BaseModel) -> tuple[dict, str, list[Evidence]]:
        """Run the dispatch in a daemon worker with a hard wall-clock wait.

        Rationale: a context-managed ThreadPoolExecutor blocks on exit
        (``shutdown(wait=True)``) until the running task finishes — so a
        "timed out" tool call would still stall the agent for as long as the
        SDK call takes, defeating the timeout. Python offers no way to cancel
        a thread blocked in an SDK call (cancellation is cooperative and the
        google-cloud/boto3 clients expose none mid-call), so instead:

        - the worker is a **daemon** thread: an abandoned call never blocks
          agent progress or process shutdown;
        - its result/exception is discarded after timeout. Workers never
          mutate executor state: evidence ids are assigned by the caller
          thread only after an accepted return (_assign_evidence_ids), and
          each worker writes into its own local ``outcome`` dict;
        - abandoned workers are counted and capped per investigation
          (MAX_ABANDONED_WORKERS), and every live worker — including
          abandoned ones — holds an application-wide WORKER_SLOTS slot until
          its underlying call actually returns, bounding total tool threads
          across all concurrent investigations
          (``max_concurrent_tool_workers``, default 16);
        - first-line defense remains the SDKs' own connect/read timeouts and
          bounded retries configured in the provider adapters, plus the
          overall investigation deadline enforced by the runner.
        """
        if self._abandoned_workers >= MAX_ABANDONED_WORKERS:
            raise WorkerBudgetExhausted(
                f"Abandoned-worker budget exhausted ({MAX_ABANDONED_WORKERS} timed-out calls); "
                "refusing further tool execution for this investigation."
            )

        token = WORKER_SLOTS.try_acquire()
        if token is None:
            raise WorkerBudgetExhausted(
                f"Application-wide tool worker limit reached "
                f"({self.settings.max_concurrent_tool_workers} concurrent workers, including "
                "ones abandoned by timeouts); refusing to spawn more. Retry when load drops."
            )

        outcome: dict[str, Any] = {}
        done = threading.Event()

        def target() -> None:
            try:
                outcome["value"] = self._dispatch(tool, args)
            except BaseException as exc:  # propagated to caller below
                outcome["error"] = exc
            finally:
                done.set()
                # Slot is held until the underlying call truly finishes —
                # releasing here (not in the caller) is what makes abandoned
                # workers count against the global bound while they live.
                WORKER_SLOTS.release(token)

        worker = threading.Thread(
            target=target,
            daemon=True,
            name=f"tool-{tool}-{self.investigation_id}",
        )
        try:
            worker.start()
        except BaseException:
            WORKER_SLOTS.release(token)  # thread never ran; return its slot
            raise
        if not done.wait(self.settings.tool_timeout_seconds):
            self._abandoned_workers += 1
            raise ToolTimeout()
        if "error" in outcome:
            raise outcome["error"]
        return outcome["value"]

    # -- dispatchers ---------------------------------------------------------

    def _dispatch(self, tool: str, args: BaseModel) -> tuple[dict, str, list[Evidence]]:
        if tool == "list_resources":
            return self._list_resources()
        if tool == "get_resource_metadata":
            return self._get_metadata(args)  # type: ignore[arg-type]
        if tool == "get_metrics":
            return self._get_metrics(args)  # type: ignore[arg-type]
        return self._query_logs(args)  # type: ignore[arg-type]

    def _list_resources(self) -> tuple[dict, str, list[Evidence]]:
        resources = self.adapter.list_resources()
        listing = [
            {"id": r.id, "name": r.name, "type": r.type, "status": r.status, "zone": r.zone or r.region}
            for r in resources
        ]
        output = {"resources": listing}
        evidence = Evidence(
            id=PENDING_EVIDENCE_ID,
            type="metadata",
            source_tool="list_resources",
            title=f"Resource inventory ({self.adapter.id})",
            summary=f"{len(listing)} resources visible to the agent.",
            data=self._bound_payload(output),
            simulated=self.adapter.simulated,
        )
        return output, f"{len(listing)} resources found", [evidence]

    def _get_metadata(self, args: GetResourceMetadataInput) -> tuple[dict, str, list[Evidence]]:
        detail = self.adapter.get_resource(args.resource_id)
        data = json.loads(detail.model_dump_json())
        # Labels can be attacker-controlled — sanitize before storage/LLM use.
        data["labels"] = {k[:100]: sanitize_untrusted(str(v), 200) for k, v in data.get("labels", {}).items()}
        summary = (
            f"{detail.type} '{detail.name}' status={detail.status}"
            f" zone={detail.zone or detail.region or 'n/a'} machine={detail.machine_type or 'n/a'}"
        )
        evidence = Evidence(
            id=PENDING_EVIDENCE_ID,
            type="metadata",
            source_tool="get_resource_metadata",
            title=f"Metadata for {detail.name}",
            summary=summary,
            data=self._bound_payload(data),
            simulated=self.adapter.simulated,
        )
        return data, summary, [evidence]

    def _get_metrics(self, args: GetMetricsInput) -> tuple[dict, str, list[Evidence]]:
        start = args.start or self.window.start
        end = args.end or self.window.end
        points, unit = self.adapter.get_metrics(
            args.resource_id, args.metric, start, end, args.step_seconds
        )
        raw = [(p.timestamp, p.value) for p in points]
        stats = summarize_series(raw, unit)
        output = {
            "metric": args.metric,
            "unit": unit,
            "stats": stats,
            "points": [{"timestamp": p.timestamp.isoformat(), "value": p.value} for p in points],
        }
        if stats.get("count"):
            summary = (
                f"{stats['count']} points; min {stats['min']}, max {stats['max']}, "
                f"avg {stats['avg']}, last {stats['last']} {unit}"
            )
        else:
            summary = f"No data points returned for {args.metric}"
        evidence = Evidence(
            id=PENDING_EVIDENCE_ID,
            type="metric",
            source_tool="get_metrics",
            title=f"{args.metric} for {args.resource_id}",
            summary=summary,
            data=self._bound_payload(output),
            simulated=self.adapter.simulated,
        )
        return output, summary, [evidence]

    def _query_logs(self, args: QueryLogsInput) -> tuple[dict, str, list[Evidence]]:
        start = args.start or self.window.start
        end = args.end or self.window.end
        limit = min(args.limit, self.settings.log_query_max_limit)
        entries, total = self.adapter.query_logs(
            args.resource_id, start, end,
            min_severity=args.min_severity, query=args.query, limit=limit,
        )
        injection_flagged = 0
        rendered = []
        for e in entries:
            message = sanitize_untrusted(e.message)
            if detect_injection(message):
                injection_flagged += 1
            rendered.append({
                "timestamp": e.timestamp.isoformat(),
                "severity": e.severity,
                "source": e.source,
                "message": message,
            })
        by_severity: dict[str, int] = {}
        for e in rendered:
            by_severity[e["severity"]] = by_severity.get(e["severity"], 0) + 1
        output = {
            "total_matched": total,
            "returned": len(rendered),
            "by_severity": by_severity,
            "injection_flagged": injection_flagged,
            "entries": rendered,
        }
        sev_summary = ", ".join(f"{v} {k}" for k, v in sorted(by_severity.items())) or "none"
        summary = f"{total} log entries matched (≥{args.min_severity}); returned {len(rendered)} ({sev_summary})"
        if injection_flagged:
            summary += f"; {injection_flagged} entries flagged as possible prompt-injection content"
        evidence = Evidence(
            id=PENDING_EVIDENCE_ID,
            type="log",
            source_tool="query_logs",
            title=f"Logs for {args.resource_id} (≥{args.min_severity})",
            summary=summary,
            data=self._bound_payload(output),
            simulated=self.adapter.simulated,
        )
        return output, summary, [evidence]

    def _bound_payload(self, data: dict) -> dict:
        """Cap stored evidence payload size (keeps DB rows and prompts bounded)."""
        limit = self.settings.max_evidence_payload_bytes
        encoded = json.dumps(data, default=str)
        if len(encoded) <= limit:
            return data
        trimmed = dict(data)
        for key in ("points", "entries", "resources"):
            if key in trimmed and isinstance(trimmed[key], list):
                while trimmed[key] and len(json.dumps(trimmed, default=str)) > limit:
                    # Drop from the middle to keep both edges of the window.
                    del trimmed[key][len(trimmed[key]) // 2]
                trimmed[f"{key}_truncated"] = True
        return trimmed
