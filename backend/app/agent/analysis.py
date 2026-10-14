"""Deterministic evidence analysis.

Used by the mock planner's reporting stage and as the grounding baseline for
LLM reports. Every statement is computed from actual tool outputs stored as
evidence — nothing here invents numbers.
"""

from __future__ import annotations

import re
from typing import Any

from ..schemas import ObservedFact, PossibleCause, Recommendation, Report


def _metric_evidence(evidence: list[dict]) -> list[dict]:
    return [e for e in evidence if e["type"] == "metric" and e.get("data", {}).get("stats", {}).get("count")]


def _log_evidence(evidence: list[dict]) -> list[dict]:
    return [e for e in evidence if e["type"] == "log"]


def analyze_evidence(evidence: list[dict]) -> dict[str, Any]:
    """Extract grounded findings from collected evidence."""
    findings: dict[str, Any] = {
        "facts": [],          # list[(statement, [evidence_ids])]
        "signals": set(),     # tags driving cause inference
        "error_samples": [],
        "injection_flagged": 0,
        "deploy_events": [],
    }

    for ev in _metric_evidence(evidence):
        data = ev["data"]
        stats = data["stats"]
        metric = data.get("metric", "")
        points = data.get("points", [])
        values = [p["value"] for p in points]
        eid = [ev["id"]]

        if metric == "cpu_utilization":
            high = sum(1 for v in values if v > 85)
            if stats["max"] > 90 and values:
                pct = round(100 * high / len(values))
                findings["facts"].append((
                    f"CPU utilization peaked at {stats['max']}% and exceeded 85% in {pct}% "
                    f"of samples in the window (avg {stats['avg']}%).", eid))
                findings["signals"].add("cpu_saturation")
            elif stats["max"] > 75:
                findings["facts"].append((f"CPU utilization is elevated (max {stats['max']}%).", eid))
                findings["signals"].add("cpu_elevated")

        elif metric == "memory_available_mb":
            if stats["last"] < 512:
                findings["facts"].append((
                    f"Available memory fell to {stats['last']} MB (started at {stats['first']} MB).", eid))
                findings["signals"].add("memory_exhaustion")
            if stats["first"] > 0 and stats["last"] < stats["first"] * 0.5 and stats["first"] > 1000:
                findings["facts"].append((
                    f"Available memory declined steadily from {stats['first']} MB to {stats['last']} MB "
                    f"— a {round(100 * (1 - stats['last'] / stats['first']))}% drop over the window.", eid))
                findings["signals"].add("memory_decline")

        elif metric == "disk_used_percent":
            if stats["last"] > 85:
                findings["facts"].append((
                    f"Disk usage reached {stats['last']}% (from {stats['first']}% at window start).", eid))
                findings["signals"].add("disk_pressure")
            elif stats["last"] - stats["first"] > 8:
                findings["facts"].append((
                    f"Disk usage grew {round(stats['last'] - stats['first'], 1)} points during the window.", eid))
                findings["signals"].add("disk_growth")

        elif metric == "http_5xx_count":
            if stats["max"] > 10:
                findings["facts"].append((
                    f"HTTP 5xx responses spiked to {stats['max']}/min (baseline near {stats['min']}).", eid))
                findings["signals"].add("error_spike")

        elif metric == "http_request_count":
            if values and stats["max"] > 2 * max(stats["min"], 1):
                findings["facts"].append((
                    f"Request volume rose from ~{stats['min']} to {stats['max']} requests/min.", eid))
                findings["signals"].add("traffic_surge")

        elif metric == "latency_ms_p95":
            if stats["first"] > 0 and stats["last"] > 2 * stats["first"]:
                findings["facts"].append((
                    f"p95 latency increased from ~{stats['first']} ms to {stats['last']} ms "
                    f"({round(stats['last'] / stats['first'], 1)}x).", eid))
                findings["signals"].add("latency_regression")
            elif stats["max"] > 500:
                findings["facts"].append((f"p95 latency peaked at {stats['max']} ms.", eid))
                findings["signals"].add("latency_elevated")

        elif metric in ("network_in_bytes", "network_out_bytes"):
            if values and stats["max"] > 4 * max(stats["min"], 1):
                direction = "inbound" if metric == "network_in_bytes" else "outbound"
                findings["facts"].append((
                    f"{direction.capitalize()} network traffic spiked to "
                    f"{round(stats['max'] / 1e6, 1)} MB/min "
                    f"({round(stats['max'] / max(stats['min'], 1))}x the window minimum).",
                    eid))
                findings["signals"].add("network_spike")

    for ev in _log_evidence(evidence):
        data = ev.get("data", {})
        entries = data.get("entries", [])
        eid = [ev["id"]]
        findings["injection_flagged"] += data.get("injection_flagged", 0)

        errors = [e for e in entries if e["severity"] in ("ERROR", "CRITICAL")]
        if errors:
            findings["facts"].append((
                f"{len(errors)} ERROR/CRITICAL log entries in the window; first at {errors[0]['timestamp']}.",
                eid))
            findings["error_samples"].extend(
                [{"message": e["message"], "evidence_id": ev["id"]} for e in errors[:4]]
            )

        text = " \n".join(e["message"] for e in entries).lower()
        if re.search(r"deployment (started|completed)", text):
            deploys = [e for e in entries if "deployment" in e["message"].lower()]
            findings["deploy_events"] = [
                {"message": d["message"], "timestamp": d["timestamp"], "evidence_id": ev["id"]}
                for d in deploys[:3]
            ]
            findings["signals"].add("deployment_event")
        if "pool exhausted" in text or "connection slots" in text or "connection pool" in text:
            findings["signals"].add("db_pool_exhaustion")
        if "oom" in text or "out of memory" in text or "killed process" in text:
            findings["signals"].add("oom_kill")
        if "no space" in text or "disk usage" in text:
            findings["signals"].add("disk_log_warning")
        if "concurrency limiter disabled" in text or "jobs enqueued" in text or "retry storm" in text:
            findings["signals"].add("batch_burst")
        if "worker pool saturated" in text or "workers busy" in text:
            findings["signals"].add("worker_saturation")
        if "autoscaler" in text and ("max" in text or "capacity" in text):
            findings["signals"].add("autoscaler_limit")

    return findings


_NO_EXCLUDE: frozenset[str] = frozenset()

_CAUSE_EXCLUSIONS: dict[str, frozenset[str]] = {
    # A steady memory decline under a traffic/batch surge is load-driven, not a leak.
    "Memory leak in the application process": frozenset({"traffic_surge", "network_spike", "batch_burst"}),
}

_CAUSE_RULES: list[tuple[frozenset[str], str, str, str]] = [
    # (required signals, cause, likelihood-if-all-present, rationale)
    (frozenset({"cpu_saturation", "traffic_surge"}),
     "Traffic surge beyond provisioned capacity",
     "likely",
     "CPU saturation coincides with a multi-x increase in request volume."),
    (frozenset({"cpu_saturation", "worker_saturation"}),
     "Worker pool saturation under load (requests queueing)",
     "likely",
     "Application logs report a saturated worker pool and queue growth while CPU is pinned."),
    (frozenset({"memory_decline"}),
     "Memory leak in the application process",
     "likely",
     "Available memory declined monotonically without a matching traffic increase."),
    (frozenset({"memory_exhaustion", "oom_kill"}),
     "Process terminated by the kernel OOM killer after memory exhaustion",
     "likely",
     "Kernel logs record an OOM kill while available memory approached zero."),
    (frozenset({"error_spike", "db_pool_exhaustion"}),
     "Database connection pool exhaustion causing request failures",
     "likely",
     "5xx spike correlates with explicit pool-exhaustion and connection-slot errors in logs."),
    (frozenset({"latency_regression", "deployment_event"}),
     "Performance regression introduced by the most recent deployment",
     "likely",
     "p95 latency step-changed immediately after the deployment event recorded in logs."),
    (frozenset({"disk_pressure"}),
     "Storage capacity nearing exhaustion from sustained data ingest",
     "likely",
     "Disk usage climbed steadily through the window and crossed the warning threshold."),
    (frozenset({"network_spike", "batch_burst"}),
     "Unthrottled batch job burst overloading the instance",
     "likely",
     "Inbound traffic spiked by several multiples alongside logs showing a released job backlog "
     "with concurrency limits disabled."),
    (frozenset({"cpu_saturation"}),
     "Runaway or inefficient process consuming CPU",
     "possible",
     "CPU is saturated; no direct process-level profile is available to confirm the consumer."),
    (frozenset({"error_spike"}),
     "Upstream dependency failure propagating as 5xx responses",
     "possible",
     "Errors are present; dependency health was not directly measured in this investigation."),
    (frozenset({"latency_regression"}),
     "Resource contention or configuration change degrading latency",
     "possible",
     "Latency regressed during the window; no deployment marker was confirmed."),
]

_RECOMMENDATIONS: dict[str, list[Recommendation]] = {
    "cpu_saturation": [
        Recommendation(action="Scale out the instance group (add capacity) or raise autoscaler limits.",
                       risk="low", rationale="Relieves saturation without changing application behavior."),
        Recommendation(action="Profile the hot process (e.g. py-spy/perf) to identify the dominant consumer.",
                       risk="low", rationale="Read-only diagnosis confirming the saturation source."),
    ],
    "memory_decline": [
        Recommendation(action="Capture a heap profile and compare object counts over time to locate the leak.",
                       risk="low", rationale="Confirms the leaking allocation site before code changes."),
        Recommendation(action="Schedule a rolling restart of the service as a temporary mitigation.",
                       risk="medium", rationale="Restores headroom but briefly reduces capacity during restart."),
    ],
    "memory_exhaustion": [
        Recommendation(action="Increase instance memory or lower the process cache ceiling as a stopgap.",
                       risk="medium", rationale="Prevents repeat OOM kills while the leak is investigated."),
    ],
    "db_pool_exhaustion": [
        Recommendation(action="Audit slow queries holding connections; add statement timeouts.",
                       risk="low", rationale="Targets the root of pool starvation."),
        Recommendation(action="Right-size the connection pool and add bounded request queuing.",
                       risk="medium", rationale="Config change; validate under load before production rollout."),
    ],
    "deployment_event": [
        Recommendation(action="Roll back to the previous release and re-measure p95 latency.",
                       risk="medium",
                       rationale="Fastest validated path to restore the SLO if the deploy is the cause."),
        Recommendation(action="Diff the release (code + config flags) for changes on the hot path.",
                       risk="low", rationale="Identifies the specific regression before rollback/fix."),
    ],
    "disk_pressure": [
        Recommendation(action="Expand the data disk or attach additional storage.",
                       risk="low", rationale="Immediate headroom; no data loss risk."),
        Recommendation(action="Review retention/compaction policy for the largest tables or paths.",
                       risk="low", rationale="Addresses growth rate rather than symptoms."),
    ],
    "batch_burst": [
        Recommendation(action="Re-enable/bound the batch concurrency limiter and drain the retry storm.",
                       risk="medium", rationale="Logs show the limiter was disabled by a config override."),
        Recommendation(action="Spread released job backlogs with ramped scheduling.",
                       risk="low", rationale="Prevents synchronized thundering-herd load."),
    ],
    "traffic_surge": [
        Recommendation(action="Verify CDN/cache hit rates and enable request-level caching for hot endpoints.",
                       risk="low", rationale="Reduces origin load under surge conditions."),
    ],
    "error_spike": [
        Recommendation(action="Check dependency health (database, upstream APIs) for the error window.",
                       risk="low", rationale="Errors reference upstream timeouts; confirm the dependency side."),
    ],
}


def build_report(question: str, evidence: list[dict], steps: list[dict], simulated: bool) -> Report:
    findings = analyze_evidence(evidence)
    facts = [ObservedFact(statement=s, evidence_ids=ids) for s, ids in findings["facts"]]

    signals: set[str] = findings["signals"]
    causes: list[PossibleCause] = []
    matched_signals: set[str] = set()
    for required, cause, likelihood, rationale in _CAUSE_RULES:
        excluded = _CAUSE_EXCLUSIONS.get(cause, _NO_EXCLUDE)
        if required <= signals and not (excluded & signals):
            ev_ids = sorted({eid for s, ids in findings["facts"] for eid in ids})[:4]
            causes.append(PossibleCause(cause=cause, likelihood=likelihood, rationale=rationale, evidence_ids=ev_ids))  # type: ignore[arg-type]
            matched_signals |= required
        if len(causes) >= 3:
            break

    recommendations: list[Recommendation] = []
    seen_actions: set[str] = set()
    for signal in sorted(matched_signals | signals):
        for rec in _RECOMMENDATIONS.get(signal, []):
            if rec.action not in seen_actions:
                recommendations.append(rec)
                seen_actions.add(rec.action)
        if len(recommendations) >= 5:
            break

    # Severity
    if {"error_spike", "oom_kill"} & signals or ("disk_pressure" in signals and any("9" in f.statement for f in facts)):
        severity = "critical" if "error_spike" in signals or "oom_kill" in signals else "high"
    elif {"cpu_saturation", "memory_exhaustion", "memory_decline", "network_spike"} & signals:
        severity = "high"
    elif {"latency_regression", "disk_pressure", "disk_growth", "deployment_event"} & signals:
        severity = "medium"
    else:
        severity = "low"

    metric_facts = any(e["type"] == "metric" for e in evidence) and bool(findings["facts"])
    log_corroboration = bool(findings["error_samples"]) or bool(findings["deploy_events"]) or bool(
        {"db_pool_exhaustion", "oom_kill", "batch_burst", "worker_saturation",
         "autoscaler_limit", "disk_log_warning"} & signals
    )
    if metric_facts and log_corroboration and causes:
        confidence = "high"
    elif facts:
        confidence = "medium"
    else:
        confidence = "low"

    limitations = [
        "Analysis is limited to the selected time window and the metrics/logs retrieved by the agent's tools.",
        "Metrics are sampled at ~60s resolution; sub-minute behavior may be missed.",
        "No process-level profiling or distributed tracing was available to this investigation.",
    ]
    if simulated:
        limitations.insert(0, "All underlying telemetry is SIMULATED demo data, clearly labeled as such.")
    if findings["injection_flagged"]:
        limitations.append(
            f"{findings['injection_flagged']} log entr{'y' if findings['injection_flagged'] == 1 else 'ies'} "
            "contained instruction-like content and were treated strictly as untrusted data "
            "(possible prompt injection)."
        )
    failed = [s for s in steps if s.get("status") == "failed"]
    if failed:
        limitations.append(f"{len(failed)} tool call(s) failed and their data is unavailable to this analysis.")

    if not facts:
        summary = (
            "The investigation did not find metric threshold breaches or significant error activity in the "
            "retrieved telemetry for this time window. No root cause can be asserted from the available evidence."
        )
        severity = "low"
        causes = []
        recommendations = recommendations or [
            Recommendation(
                action="Widen the time window or add metrics/log sources, then re-run the investigation.",
                risk="low", rationale="Current evidence is insufficient to establish any finding.",
            )
        ]
    else:
        top_cause = causes[0].cause if causes else "an undetermined cause"
        n_logs = len([e for e in evidence if e["type"] == "log"])
        summary = (
            f"Evidence from {len([e for e in evidence if e['type'] == 'metric'])} metric series and "
            f"{n_logs} log quer{'y' if n_logs == 1 else 'ies'} shows: {facts[0].statement} "
            f"The most consistent explanation is: {top_cause[0].lower() + top_cause[1:]}."
        )

    return Report(
        summary=summary,
        severity_assessment=severity,  # type: ignore[arg-type]
        observed_facts=facts,
        possible_causes=causes,
        recommendations=recommendations,
        confidence=confidence,  # type: ignore[arg-type]
        limitations=limitations,
        llm_provider="mock",
    )
