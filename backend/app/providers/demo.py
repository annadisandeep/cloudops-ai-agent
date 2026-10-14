"""Demo provider adapter — serves deterministic synthetic data (no credentials).

A single adapter emulates both GCP- and AWS-shaped resources; the API layer
routes ``provider=gcp|aws`` here when demo mode is active. Every object is
labeled ``simulated``.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from ..demo import data as demo
from ..errors import NotFoundError, ValidationApiError
from ..schemas import LogEntry, MetricPoint, Resource, ResourceDetail
from .base import ProviderAdapter


def _to_resource(r: demo.DemoResource) -> Resource:
    return Resource(
        id=r.id,
        provider=r.provider,  # type: ignore[arg-type]
        account=r.account,
        name=r.name,
        type=r.type,
        zone=r.zone,
        region=r.region,
        status=r.status,
        machine_type=r.machine_type,
        internal_ip=r.internal_ip,
        external_ip=r.external_ip,
        labels=dict(r.labels),
        created_at=demo.anchor_now() - timedelta(days=r.created_days_ago),
        simulated=True,
    )


class DemoAdapter(ProviderAdapter):
    id = "demo"

    def __init__(self, emulated_provider: str | None = None) -> None:
        """emulated_provider filters to gcp- or aws-shaped demo resources."""
        self._emulated = emulated_provider

    @property
    def simulated(self) -> bool:
        return True

    def _resources(self) -> list[demo.DemoResource]:
        if self._emulated in ("gcp", "aws"):
            return [r for r in demo.RESOURCES if r.provider == self._emulated]
        return list(demo.RESOURCES)

    def list_resources(self, account: str | None = None) -> list[Resource]:
        resources = self._resources()
        if account:
            resources = [r for r in resources if r.account == account]
        return [_to_resource(r) for r in resources]

    def _get_demo_resource(self, resource_id: str) -> demo.DemoResource:
        r = demo.RESOURCE_INDEX.get(resource_id)
        if r is None or (self._emulated in ("gcp", "aws") and r.provider != self._emulated):
            raise NotFoundError(f"Resource '{resource_id}' not found")
        return r

    def get_resource(self, resource_id: str) -> ResourceDetail:
        r = self._get_demo_resource(resource_id)
        base = _to_resource(r)
        return ResourceDetail(
            **base.model_dump(),
            scenario_ids=[s.id for s in demo.scenarios_for_resource(r.id)],
        )

    def get_metrics(
        self,
        resource_id: str,
        metric: str,
        start: datetime,
        end: datetime,
        step_seconds: int = 60,
    ) -> tuple[list[MetricPoint], str]:
        self._get_demo_resource(resource_id)
        if metric not in demo.METRIC_UNITS:
            raise ValidationApiError(
                f"Unknown metric '{metric}'. Available: {', '.join(sorted(demo.METRIC_UNITS))}"
            )
        series = demo.metric_series(resource_id, metric, start, end, step_seconds)
        return (
            [MetricPoint(timestamp=ts, value=v) for ts, v in series],
            demo.METRIC_UNITS[metric],
        )

    def query_logs(
        self,
        resource_id: str,
        start: datetime,
        end: datetime,
        min_severity: str = "DEBUG",
        query: str | None = None,
        limit: int = 100,
    ) -> tuple[list[LogEntry], int]:
        self._get_demo_resource(resource_id)
        entries, total = demo.log_entries(
            resource_id, start, end, min_severity=min_severity, query=query, limit=limit
        )
        return [LogEntry(**e) for e in entries], total
