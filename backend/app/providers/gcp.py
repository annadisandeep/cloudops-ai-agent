"""GCP read-only adapter (Compute Engine, Cloud Monitoring, Cloud Logging).

- Uses Application Default Credentials (ADC) on the server; credentials never
  reach the browser.
- Only read/list operations are implemented — the adapter has no mutating
  methods by design.
- The project must be present in ``CLOUDOPS_GCP_ALLOWED_PROJECTS`` (fail closed).
- Cloud client libraries are imported lazily so demo mode runs without them.

Status: implemented and mock-tested. Not yet verified against a live project.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from ..config import get_settings
from ..errors import ApiError, NotFoundError, ProviderDisabledError, ValidationApiError
from ..schemas import LogEntry, MetricPoint, Resource, ResourceDetail
from .base import ProviderAdapter

logger = logging.getLogger("cloudops.providers.gcp")

# Our metric names -> (Cloud Monitoring metric type, unit, value transform)
GCP_METRIC_MAP: dict[str, tuple[str, str, float]] = {
    "cpu_utilization": ("compute.googleapis.com/instance/cpu/utilization", "percent", 100.0),
    "network_in_bytes": ("compute.googleapis.com/instance/network/received_bytes_count", "bytes", 1.0),
    "network_out_bytes": ("compute.googleapis.com/instance/network/sent_bytes_count", "bytes", 1.0),
    # The following require the Ops Agent on the VM:
    "memory_available_mb": ("agent.googleapis.com/memory/bytes_used", "MB", 1.0 / (1024 * 1024)),
    "disk_used_percent": ("agent.googleapis.com/disk/percent_used", "percent", 1.0),
}

MAX_LIST_PAGES = 10
LOG_PAGE_SIZE = 100


class GcpAdapter(ProviderAdapter):
    id = "gcp"

    def __init__(self, project: str) -> None:
        settings = get_settings()
        if not settings.gcp_enabled:
            raise ProviderDisabledError("GCP provider is not enabled.")
        if project not in settings.gcp_allowed_project_list:
            raise ProviderDisabledError(
                f"GCP project '{project}' is not in the configured allowlist."
            )
        self.project = project
        self._timeout = settings.tool_timeout_seconds

    # -- lazy clients -------------------------------------------------------

    def _compute_client(self):
        try:
            from google.cloud import compute_v1
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise ApiError("dependency_missing", "google-cloud-compute is not installed.", 500) from exc
        return compute_v1.InstancesClient()

    def _monitoring_client(self):
        try:
            from google.cloud import monitoring_v3
        except ImportError as exc:  # pragma: no cover
            raise ApiError("dependency_missing", "google-cloud-monitoring is not installed.", 500) from exc
        return monitoring_v3.MetricServiceClient()

    def _logging_client(self):
        try:
            from google.cloud import logging as gcp_logging
        except ImportError as exc:  # pragma: no cover
            raise ApiError("dependency_missing", "google-cloud-logging is not installed.", 500) from exc
        return gcp_logging.Client(project=self.project)

    # -- operations ---------------------------------------------------------

    def list_resources(self, account: str | None = None) -> list[Resource]:
        client = self._compute_client()
        resources: list[Resource] = []
        pages = 0
        # aggregated_list paginates across all zones.
        for zone_path, scoped in client.aggregated_list(
            project=self.project, timeout=self._timeout
        ):
            pages += 1
            if pages > MAX_LIST_PAGES * 50:  # hard bound on zone buckets processed
                logger.warning("GCP aggregated_list truncated at bound for %s", self.project)
                break
            for inst in getattr(scoped, "instances", []) or []:
                resources.append(self._instance_to_resource(inst, zone_path))
        return resources

    def _instance_to_resource(self, inst, zone_path: str) -> Resource:
        zone = zone_path.split("/")[-1] if zone_path else None
        internal_ip = None
        external_ip = None
        for nic in getattr(inst, "network_interfaces", []) or []:
            internal_ip = internal_ip or getattr(nic, "network_i_p", None)
            for ac in getattr(nic, "access_configs", []) or []:
                external_ip = external_ip or getattr(ac, "nat_i_p", None)
        machine_type = (inst.machine_type or "").split("/")[-1] or None
        created = None
        if getattr(inst, "creation_timestamp", None):
            try:
                created = datetime.fromisoformat(inst.creation_timestamp)
            except ValueError:
                created = None
        return Resource(
            id=inst.name,
            provider="gcp",
            account=self.project,
            name=inst.name,
            type="compute-instance",
            zone=zone,
            status=(inst.status or "unknown").lower(),
            machine_type=machine_type,
            internal_ip=internal_ip,
            external_ip=external_ip,
            labels=dict(getattr(inst, "labels", {}) or {}),
            created_at=created,
            simulated=False,
        )

    def get_resource(self, resource_id: str) -> ResourceDetail:
        for r in self.list_resources():
            if r.id == resource_id:
                return ResourceDetail(**r.model_dump(), scenario_ids=[])
        raise NotFoundError(f"Instance '{resource_id}' not found in project {self.project}")

    def get_metrics(
        self,
        resource_id: str,
        metric: str,
        start: datetime,
        end: datetime,
        step_seconds: int = 60,
    ) -> tuple[list[MetricPoint], str]:
        if metric not in GCP_METRIC_MAP:
            raise ValidationApiError(
                f"Metric '{metric}' is not mapped for GCP. Available: {', '.join(sorted(GCP_METRIC_MAP))}"
            )
        metric_type, unit, factor = GCP_METRIC_MAP[metric]
        from google.cloud import monitoring_v3

        client = self._monitoring_client()
        interval = monitoring_v3.TimeInterval(
            start_time={"seconds": int(start.timestamp())},
            end_time={"seconds": int(end.timestamp())},
        )
        aggregation = monitoring_v3.Aggregation(
            alignment_period={"seconds": max(step_seconds, 60)},
            per_series_aligner=monitoring_v3.Aggregation.Aligner.ALIGN_MEAN,
        )
        results = client.list_time_series(
            request={
                "name": f"projects/{self.project}",
                "filter": (
                    f'metric.type = "{metric_type}" AND '
                    f'metric.labels.instance_name = "{resource_id}"'
                ),
                "interval": interval,
                "aggregation": aggregation,
                "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
            },
            timeout=self._timeout,
        )
        points: list[MetricPoint] = []
        for series in results:
            for p in series.points:
                ts = datetime.fromtimestamp(p.interval.end_time.timestamp(), tz=UTC)
                value = p.value.double_value or float(p.value.int64_value)
                points.append(MetricPoint(timestamp=ts, value=round(value * factor, 4)))
        points.sort(key=lambda p: p.timestamp)
        return points, unit

    def query_logs(
        self,
        resource_id: str,
        start: datetime,
        end: datetime,
        min_severity: str = "DEBUG",
        query: str | None = None,
        limit: int = 100,
    ) -> tuple[list[LogEntry], int]:
        client = self._logging_client()
        # Bounded, parameter-validated filter. resource_id/severity come from
        # validated enums/identifiers upstream; quotes are stripped defensively.
        safe_id = resource_id.replace('"', "")
        filter_parts = [
            'resource.type="gce_instance"',
            f'(resource.labels.instance_id="{safe_id}" OR labels."compute.googleapis.com/resource_name"="{safe_id}")',
            f'timestamp>="{start.isoformat()}"',
            f'timestamp<="{end.isoformat()}"',
        ]
        if min_severity.upper() != "DEBUG":
            filter_parts.append(f"severity>={min_severity.upper()}")
        entries: list[LogEntry] = []
        iterator = client.list_entries(
            filter_=" AND ".join(filter_parts),
            order_by="timestamp desc",
            page_size=min(limit, LOG_PAGE_SIZE),
        )
        for entry in iterator:
            message = entry.payload if isinstance(entry.payload, str) else str(entry.payload)
            if query and query.lower() not in message.lower():
                continue
            entries.append(
                LogEntry(
                    timestamp=entry.timestamp,
                    severity=(entry.severity or "INFO").upper(),  # type: ignore[arg-type]
                    message=message[:4000],
                    source=entry.log_name.split("/")[-1] if entry.log_name else "gcp",
                )
            )
            if len(entries) >= limit:
                break
        entries.sort(key=lambda e: e.timestamp)
        return entries, len(entries)
