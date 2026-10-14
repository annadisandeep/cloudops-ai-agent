"""REST API (v1) — see docs/API.md for the contract."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Query, Response

from .. import db
from ..agent import runner
from ..agent.report import render_markdown
from ..config import get_settings
from ..demo.data import SCENARIOS, scenario_window
from ..errors import NotFoundError, ValidationApiError
from ..providers.registry import get_adapter
from ..schemas import (
    Account,
    AttentionItem,
    ConfigResponse,
    HealthResponse,
    Investigation,
    InvestigationCreate,
    InvestigationListResponse,
    InvestigationSummary,
    Limits,
    LlmInfo,
    LogsResponse,
    MetricsResponse,
    OverviewResponse,
    ProviderInfo,
    ProviderListResponse,
    ProviderStatus,
    ResourceDetail,
    ResourceListResponse,
    Scenario,
    ScenarioListResponse,
    TimeWindow,
)

router = APIRouter(prefix="/api/v1")

ProviderParam = Literal["demo", "gcp", "aws"]


def _default_window(start: datetime | None, end: datetime | None) -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    end = end or now
    start = start or end - timedelta(hours=1)
    if end <= start:
        raise ValidationApiError("'end' must be after 'start'")
    if end - start > timedelta(days=7):
        raise ValidationApiError("Time range must be 7 days or shorter")
    return start, end


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", version=settings.version, time=datetime.now(UTC))


@router.get("/config", response_model=ConfigResponse, tags=["system"])
def config() -> ConfigResponse:
    s = get_settings()
    return ConfigResponse(
        demo_mode=s.demo_mode,
        providers={
            "demo": ProviderStatus(enabled=s.demo_mode, mode="demo"),
            "gcp": ProviderStatus(
                enabled=s.gcp_enabled, mode="read-only",
                allowed_projects=s.gcp_allowed_project_list,
            ),
            "aws": ProviderStatus(
                enabled=s.aws_enabled, mode="read-only",
                allowed_accounts=s.aws_allowed_account_list,
            ),
        },
        llm=LlmInfo(provider=s.llm_provider, model=s.llm_model_label),  # type: ignore[arg-type]
        limits=Limits(
            max_steps=s.max_steps,
            tool_timeout_seconds=s.tool_timeout_seconds,
            investigation_timeout_seconds=s.investigation_timeout_seconds,
        ),
    )


@router.get("/providers", response_model=ProviderListResponse, tags=["providers"])
def providers() -> ProviderListResponse:
    s = get_settings()
    items = [
        ProviderInfo(
            id="demo", name="Demo Environment", enabled=s.demo_mode, mode="demo",
            accounts=[Account(id="demo-project", name="Demo Project", kind="project")]
            if s.demo_mode else [],
        ),
        ProviderInfo(
            id="gcp", name="Google Cloud Platform",
            enabled=s.gcp_enabled or s.demo_mode,
            mode="demo" if (s.demo_mode and not s.gcp_enabled) else "read-only",
            accounts=(
                [Account(id=p, name=p, kind="project") for p in s.gcp_allowed_project_list]
                if s.gcp_enabled
                else ([Account(id="demo-project", name="Demo Project (simulated)", kind="project")]
                      if s.demo_mode else [])
            ),
        ),
        ProviderInfo(
            id="aws", name="Amazon Web Services",
            enabled=s.aws_enabled or s.demo_mode,
            mode="demo" if (s.demo_mode and not s.aws_enabled) else "read-only",
            accounts=(
                [Account(id=a, name=a, kind="account") for a in s.aws_allowed_account_list]
                if s.aws_enabled
                else ([Account(id="123456789012", name="Demo Account (simulated)", kind="account")]
                      if s.demo_mode else [])
            ),
        ),
    ]
    return ProviderListResponse(items=items)


@router.get("/scenarios", response_model=ScenarioListResponse, tags=["demo"])
def scenarios() -> ScenarioListResponse:
    start, end = scenario_window()
    items = [
        Scenario(
            id=s.id, title=s.title, provider=s.provider, severity=s.severity,  # type: ignore[arg-type]
            category=s.category, resource_id=s.resource_id,  # type: ignore[arg-type]
            resource_name=s.resource_id, description=s.description,
            time_window=TimeWindow(start=start, end=end),
            suggested_question=s.suggested_question, simulated=True,
        )
        for s in SCENARIOS
    ]
    return ScenarioListResponse(items=items)


@router.get("/overview", response_model=OverviewResponse, tags=["system"])
def overview() -> OverviewResponse:
    settings = get_settings()
    resources = []
    simulated = False
    for provider_id in ("gcp", "aws"):
        try:
            adapter = get_adapter(provider_id)
            resources.extend(adapter.list_resources())
            simulated = simulated or adapter.simulated
        except Exception:
            continue  # provider disabled/unreachable — overview stays partial

    by_provider: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for r in resources:
        by_provider[r.provider] = by_provider.get(r.provider, 0) + 1
        by_status[r.status] = by_status.get(r.status, 0) + 1

    attention: list[AttentionItem] = []
    if settings.demo_mode:
        reasons = {
            "gcp-high-cpu": "CPU sustained above 90%",
            "gcp-low-memory": "Available memory below 200 MB and falling",
            "app-5xx-errors": "HTTP 5xx spike in progress",
            "deploy-degradation": "p95 latency 3x after deployment v2.4.1",
            "storage-capacity": "Disk usage above 90%, projected full in days",
            "aws-ec2-performance": "CPU saturated; inbound network 8x baseline",
        }
        for s in SCENARIOS:
            attention.append(AttentionItem(
                resource_id=s.resource_id, provider=s.provider,  # type: ignore[arg-type]
                reason=reasons.get(s.id, s.title), severity=s.severity,  # type: ignore[arg-type]
                scenario_id=s.id,
            ))

    recent, _ = db.list_investigations(page=1, page_size=5)
    return OverviewResponse(
        resource_counts={
            "total": len(resources), "by_provider": by_provider, "by_status": by_status,
        },
        attention=attention,
        recent_investigations=recent,
        simulated=simulated,
    )


@router.get("/resources", response_model=ResourceListResponse, tags=["resources"])
def list_resources(
    provider: ProviderParam,
    account: str | None = Query(default=None, max_length=100),
    q: str | None = Query(default=None, max_length=200),
    type: str | None = Query(default=None, max_length=100),
    status: str | None = Query(default=None, max_length=50),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ResourceListResponse:
    adapter = get_adapter(provider, account)
    items = adapter.list_resources(account)
    if q:
        needle = q.lower()
        items = [r for r in items if needle in r.name.lower() or needle in r.id.lower()]
    if type:
        items = [r for r in items if r.type == type]
    if status:
        items = [r for r in items if r.status == status]
    total = len(items)
    start_i = (page - 1) * page_size
    return ResourceListResponse(
        items=items[start_i : start_i + page_size], total=total, page=page, page_size=page_size
    )


@router.get("/resources/{provider}/{resource_id}", response_model=ResourceDetail, tags=["resources"])
def get_resource(provider: ProviderParam, resource_id: str) -> ResourceDetail:
    return get_adapter(provider).get_resource(resource_id)


@router.get("/metrics", response_model=MetricsResponse, tags=["telemetry"])
def get_metrics(
    provider: ProviderParam,
    resource_id: str = Query(min_length=1, max_length=200),
    metric: str = Query(min_length=1, max_length=100),
    start: datetime | None = None,
    end: datetime | None = None,
    step_seconds: int = Query(default=60, ge=15, le=3600),
) -> MetricsResponse:
    start_dt, end_dt = _default_window(start, end)
    adapter = get_adapter(provider)
    points, unit = adapter.get_metrics(resource_id, metric, start_dt, end_dt, step_seconds)
    return MetricsResponse(
        provider=provider, resource_id=resource_id, metric=metric, unit=unit,
        points=points, simulated=adapter.simulated,
    )


@router.get("/logs", response_model=LogsResponse, tags=["telemetry"])
def get_logs(
    provider: ProviderParam,
    resource_id: str = Query(min_length=1, max_length=200),
    start: datetime | None = None,
    end: datetime | None = None,
    severity: str = Query(default="DEBUG", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$"),
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=500),
) -> LogsResponse:
    from ..agent.sanitize import sanitize_untrusted

    start_dt, end_dt = _default_window(start, end)
    adapter = get_adapter(provider)
    entries, total = adapter.query_logs(
        resource_id, start_dt, end_dt, min_severity=severity, query=q, limit=limit
    )
    for e in entries:
        e.message = sanitize_untrusted(e.message)
    return LogsResponse(entries=entries, total=total, simulated=adapter.simulated)


# --- Investigations -----------------------------------------------------------


@router.post("/investigations", response_model=Investigation, status_code=201, tags=["investigations"])
def create_investigation(payload: InvestigationCreate) -> Investigation:
    inv = runner.prepare_investigation(payload)
    runner.start_investigation_async(inv.id)
    inv.status = "running"
    return inv


@router.get("/investigations", response_model=InvestigationListResponse, tags=["investigations"])
def list_investigations(
    q: str | None = Query(default=None, max_length=200),
    provider: ProviderParam | None = None,
    status: str | None = Query(default=None, pattern="^(queued|running|completed|failed)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> InvestigationListResponse:
    items, total = db.list_investigations(q=q, provider=provider, status=status, page=page, page_size=page_size)
    return InvestigationListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/investigations/{inv_id}", response_model=Investigation, tags=["investigations"])
def get_investigation(inv_id: str) -> Investigation:
    inv = db.get_investigation(inv_id)
    if inv is None:
        raise NotFoundError(f"Investigation '{inv_id}' not found")
    return inv


@router.get("/investigations/{inv_id}/report.md", tags=["investigations"])
def export_report(inv_id: str) -> Response:
    inv = db.get_investigation(inv_id)
    if inv is None:
        raise NotFoundError(f"Investigation '{inv_id}' not found")
    if inv.status not in ("completed", "failed"):
        raise NotFoundError(f"Investigation '{inv_id}' has no report yet (status: {inv.status})")
    markdown = render_markdown(inv)
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{inv.id}-report.md"'},
    )


def _summary(inv: Investigation) -> InvestigationSummary:
    return InvestigationSummary(
        id=inv.id, question=inv.question, provider=inv.provider,
        resource_id=inv.resource_id, scenario_id=inv.scenario_id, status=inv.status,
        severity_assessment=inv.report.severity_assessment if inv.report else None,
        created_at=inv.created_at, completed_at=inv.completed_at,
        step_count=len(inv.steps), simulated=inv.simulated,
    )
