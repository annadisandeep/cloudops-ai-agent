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
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from ..config import get_settings
from ..errors import ApiError
from ..providers.base import ProviderAdapter
from ..schemas import Evidence, TimeWindow, ToolStep
from .sanitize import detect_injection, sanitize_untrusted

ALLOWED_TOOLS = frozenset({"list_resources", "get_resource_metadata", "get_metrics", "query_logs"})

TRANSIENT_ERRORS = (ConnectionError, TimeoutError, FutureTimeoutError)


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
    "list_resources": "List cloud resources visible to the selected provider/account.",
    "get_resource_metadata": "Fetch metadata for one resource (type, zone, status, labels, IPs).",
    "get_metrics": (
        "Fetch a metric time series for a resource. Metrics: cpu_utilization, "
        "memory_available_mb, disk_used_percent, network_in_bytes, network_out_bytes, "
        "http_5xx_count, http_request_count, latency_ms_p95."
    ),
    "query_logs": "Query log entries for a resource within a time window, filtered by minimum severity.",
}


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

    def _next_evidence_id(self) -> str:
        self._evidence_counter += 1
        return f"ev_{self._evidence_counter}"

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
            step.status = "failed"
            step.error = f"Invalid tool arguments: {'; '.join(e['msg'] for e in exc.errors()[:3])}"
            step.duration_ms = 0
            return step, []
        step.input = json.loads(args.model_dump_json(exclude_none=True))

        attempts = 0
        last_error: str | None = None
        while attempts <= self.settings.tool_retry_budget:
            attempts += 1
            try:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(self._dispatch, tool, args)
                    output, summary, evidence = future.result(
                        timeout=self.settings.tool_timeout_seconds
                    )
                step.status = "completed"
                step.output_summary = summary
                step.duration_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
                step.evidence_ids = [e.id for e in evidence]
                return step, evidence
            except FutureTimeoutError:
                last_error = f"Tool timed out after {self.settings.tool_timeout_seconds}s"
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
            id=self._next_evidence_id(),
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
            id=self._next_evidence_id(),
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
            id=self._next_evidence_id(),
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
            id=self._next_evidence_id(),
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
