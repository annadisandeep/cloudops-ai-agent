"""Provider adapter interface.

Adapters expose strictly read-only operations. Live adapters must never be
given mutating scopes and must validate the account/project against the
configured allowlist before every call.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from ..schemas import LogEntry, MetricPoint, Resource, ResourceDetail


class ProviderAdapter(ABC):
    """Read-only cloud provider adapter."""

    id: str

    @abstractmethod
    def list_resources(self, account: str | None = None) -> list[Resource]: ...

    @abstractmethod
    def get_resource(self, resource_id: str) -> ResourceDetail: ...

    @abstractmethod
    def get_metrics(
        self,
        resource_id: str,
        metric: str,
        start: datetime,
        end: datetime,
        step_seconds: int = 60,
    ) -> tuple[list[MetricPoint], str]:
        """Returns (points, unit)."""

    @abstractmethod
    def query_logs(
        self,
        resource_id: str,
        start: datetime,
        end: datetime,
        min_severity: str = "DEBUG",
        query: str | None = None,
        limit: int = 100,
    ) -> tuple[list[LogEntry], int]:
        """Returns (entries, total_matched)."""

    @property
    def simulated(self) -> bool:
        return False
