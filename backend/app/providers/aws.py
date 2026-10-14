"""AWS read-only adapter (EC2, CloudWatch, CloudWatch Logs) via boto3.

- Server-side credentials only (standard boto3 chain: env vars, shared config,
  instance profile). Nothing is exposed to the browser.
- Strictly read-only API calls: Describe*/Get*/Filter* only.
- The account must be in ``CLOUDOPS_AWS_ALLOWED_ACCOUNTS`` (fail closed) —
  verified via STS GetCallerIdentity at adapter construction.
- boto3 is imported lazily so demo mode works without it installed.

Status: implemented and mock-tested. Not yet verified against a live account.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from ..config import get_settings
from ..errors import ApiError, NotFoundError, ProviderDisabledError, ValidationApiError
from ..schemas import LogEntry, MetricPoint, Resource, ResourceDetail
from .base import ProviderAdapter

logger = logging.getLogger("cloudops.providers.aws")

# Our metric names -> (namespace, CloudWatch metric, stat, unit, transform)
AWS_METRIC_MAP: dict[str, tuple[str, str, str, str, float]] = {
    "cpu_utilization": ("AWS/EC2", "CPUUtilization", "Average", "percent", 1.0),
    "network_in_bytes": ("AWS/EC2", "NetworkIn", "Sum", "bytes", 1.0),
    "network_out_bytes": ("AWS/EC2", "NetworkOut", "Sum", "bytes", 1.0),
    # Requires the CloudWatch agent on the instance:
    "memory_available_mb": ("CWAgent", "mem_available", "Average", "MB", 1.0 / (1024 * 1024)),
    "disk_used_percent": ("CWAgent", "disk_used_percent", "Average", "percent", 1.0),
}

MAX_PAGES = 10


class AwsAdapter(ProviderAdapter):
    id = "aws"

    def __init__(self, account: str | None = None) -> None:
        settings = get_settings()
        if not settings.aws_enabled:
            raise ProviderDisabledError("AWS provider is not enabled.")
        if not settings.aws_allowed_account_list:
            raise ProviderDisabledError("No AWS accounts are allowlisted; failing closed.")
        self._settings = settings
        self._region = settings.aws_region
        self._session = self._build_session()
        self.account = self._verify_account(account)

    def _build_session(self):
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise ApiError("dependency_missing", "boto3 is not installed.", 500) from exc
        return boto3.Session(region_name=self._region)

    def _client(self, service: str):
        from botocore.config import Config

        return self._session.client(
            service,
            config=Config(
                connect_timeout=5,
                read_timeout=self._settings.tool_timeout_seconds,
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )

    def _verify_account(self, requested: str | None) -> str:
        """Fail closed unless the caller identity account is allowlisted."""
        sts = self._client("sts")
        try:
            identity = sts.get_caller_identity()
        except Exception as exc:
            raise ProviderDisabledError(f"AWS credentials unavailable or invalid: {type(exc).__name__}") from exc
        account = identity["Account"]
        allowed = self._settings.aws_allowed_account_list
        if account not in allowed or (requested and requested != account):
            raise ProviderDisabledError(f"AWS account '{account}' is not in the configured allowlist.")
        return account

    # -- operations ---------------------------------------------------------

    def list_resources(self, account: str | None = None) -> list[Resource]:
        ec2 = self._client("ec2")
        paginator = ec2.get_paginator("describe_instances")
        resources: list[Resource] = []
        for page_no, page in enumerate(paginator.paginate(PaginationConfig={"MaxItems": 500})):
            if page_no >= MAX_PAGES:
                logger.warning("EC2 describe_instances truncated at %d pages", MAX_PAGES)
                break
            for reservation in page.get("Reservations", []):
                for inst in reservation.get("Instances", []):
                    resources.append(self._instance_to_resource(inst))
        return resources

    def _instance_to_resource(self, inst: dict) -> Resource:
        tags = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}
        created = inst.get("LaunchTime")
        if created and created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        return Resource(
            id=inst["InstanceId"],
            provider="aws",
            account=self.account,
            name=tags.get("Name", inst["InstanceId"]),
            type="ec2-instance",
            region=self._region,
            zone=inst.get("Placement", {}).get("AvailabilityZone"),
            status=inst.get("State", {}).get("Name", "unknown"),
            machine_type=inst.get("InstanceType"),
            internal_ip=inst.get("PrivateIpAddress"),
            external_ip=inst.get("PublicIpAddress"),
            labels=tags,
            created_at=created,
            simulated=False,
        )

    def get_resource(self, resource_id: str) -> ResourceDetail:
        ec2 = self._client("ec2")
        try:
            result = ec2.describe_instances(InstanceIds=[resource_id])
        except Exception as exc:
            if "InvalidInstanceID" in str(exc):
                raise NotFoundError(f"EC2 instance '{resource_id}' not found") from exc
            raise
        for reservation in result.get("Reservations", []):
            for inst in reservation.get("Instances", []):
                return ResourceDetail(**self._instance_to_resource(inst).model_dump(), scenario_ids=[])
        raise NotFoundError(f"EC2 instance '{resource_id}' not found")

    def get_metrics(
        self,
        resource_id: str,
        metric: str,
        start: datetime,
        end: datetime,
        step_seconds: int = 60,
    ) -> tuple[list[MetricPoint], str]:
        if metric not in AWS_METRIC_MAP:
            raise ValidationApiError(
                f"Metric '{metric}' is not mapped for AWS. Available: {', '.join(sorted(AWS_METRIC_MAP))}"
            )
        namespace, cw_metric, stat, unit, factor = AWS_METRIC_MAP[metric]
        cw = self._client("cloudwatch")
        period = max(60, (step_seconds // 60) * 60)
        resp = cw.get_metric_statistics(
            Namespace=namespace,
            MetricName=cw_metric,
            Dimensions=[{"Name": "InstanceId", "Value": resource_id}],
            StartTime=start,
            EndTime=end,
            Period=period,
            Statistics=[stat],
        )
        points = [
            MetricPoint(
                timestamp=dp["Timestamp"].replace(tzinfo=dp["Timestamp"].tzinfo or UTC),
                value=round(dp[stat] * factor, 4),
            )
            for dp in resp.get("Datapoints", [])
        ]
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
        logs = self._client("logs")
        severity_order = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        threshold = severity_order.index(min_severity.upper()) if min_severity.upper() in severity_order else 0
        entries: list[LogEntry] = []
        kwargs = {
            "logGroupName": f"/cloudops/{resource_id}",
            "startTime": int(start.timestamp() * 1000),
            "endTime": int(end.timestamp() * 1000),
            "limit": min(limit, 100),
        }
        if query:
            kwargs["filterPattern"] = f'"{query[:200]}"'
        pages = 0
        try:
            while pages < MAX_PAGES:
                resp = logs.filter_log_events(**kwargs)
                for event in resp.get("events", []):
                    message = event.get("message", "")
                    severity = "INFO"
                    for level in reversed(severity_order):
                        if level in message[:64].upper():
                            severity = level
                            break
                    if severity_order.index(severity) < threshold:
                        continue
                    entries.append(
                        LogEntry(
                            timestamp=datetime.fromtimestamp(event["timestamp"] / 1000, tz=UTC),
                            severity=severity,  # type: ignore[arg-type]
                            message=message[:4000],
                            source=event.get("logStreamName", "cloudwatch"),
                        )
                    )
                    if len(entries) >= limit:
                        return sorted(entries, key=lambda e: e.timestamp), len(entries)
                token = resp.get("nextToken")
                if not token:
                    break
                kwargs["nextToken"] = token
                pages += 1
        except logs.exceptions.ResourceNotFoundException:
            return [], 0
        entries.sort(key=lambda e: e.timestamp)
        return entries, len(entries)
