"""Pydantic models for the public API contract (docs/API.md)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Provider = Literal["demo", "gcp", "aws"]
Severity = Literal["critical", "high", "medium", "low"]
InvestigationStatus = Literal["queued", "running", "completed", "failed"]
EvidenceType = Literal["metric", "log", "metadata"]
Likelihood = Literal["likely", "possible", "unlikely"]
Risk = Literal["low", "medium", "high"]
Confidence = Literal["high", "medium", "low"]


class TimeWindow(BaseModel):
    start: datetime
    end: datetime


# --- Config / providers ----------------------------------------------------


class ProviderStatus(BaseModel):
    enabled: bool
    mode: Literal["demo", "read-only"]
    allowed_projects: list[str] | None = None
    allowed_accounts: list[str] | None = None


class LlmInfo(BaseModel):
    provider: Literal["mock", "gemini"]
    model: str


class Limits(BaseModel):
    max_steps: int
    tool_timeout_seconds: int
    investigation_timeout_seconds: int


class ConfigResponse(BaseModel):
    demo_mode: bool
    providers: dict[str, ProviderStatus]
    llm: LlmInfo
    limits: Limits


class Account(BaseModel):
    id: str
    name: str
    kind: Literal["project", "account"]


class ProviderInfo(BaseModel):
    id: Provider
    name: str
    enabled: bool
    mode: Literal["demo", "read-only"]
    accounts: list[Account]


class ProviderListResponse(BaseModel):
    items: list[ProviderInfo]


# --- Scenarios --------------------------------------------------------------


class Scenario(BaseModel):
    id: str
    title: str
    provider: Provider
    severity: Severity
    category: Literal["performance", "memory", "errors", "deployment", "storage"]
    resource_id: str
    resource_name: str
    description: str
    time_window: TimeWindow
    suggested_question: str
    simulated: bool = True


class ScenarioListResponse(BaseModel):
    items: list[Scenario]


# --- Resources --------------------------------------------------------------


class Resource(BaseModel):
    id: str
    provider: Provider
    account: str
    name: str
    type: str
    zone: str | None = None
    region: str | None = None
    status: str
    machine_type: str | None = None
    internal_ip: str | None = None
    external_ip: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    created_at: datetime | None = None
    simulated: bool = False


class ResourceDetail(Resource):
    scenario_ids: list[str] = Field(default_factory=list)


class ResourceListResponse(BaseModel):
    items: list[Resource]
    total: int
    page: int
    page_size: int


# --- Telemetry --------------------------------------------------------------


class MetricPoint(BaseModel):
    timestamp: datetime
    value: float


class MetricsResponse(BaseModel):
    provider: Provider
    resource_id: str
    metric: str
    unit: str
    points: list[MetricPoint]
    simulated: bool = False


class LogEntry(BaseModel):
    timestamp: datetime
    severity: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    message: str
    source: str = "app"


class LogsResponse(BaseModel):
    entries: list[LogEntry]
    total: int
    simulated: bool = False


# --- Overview ---------------------------------------------------------------


class AttentionItem(BaseModel):
    resource_id: str
    provider: Provider
    reason: str
    severity: Severity
    scenario_id: str | None = None


class OverviewResponse(BaseModel):
    resource_counts: dict[str, Any]
    attention: list[AttentionItem]
    recent_investigations: list[InvestigationSummary]
    simulated: bool = False


# --- Investigations ---------------------------------------------------------


class InvestigationCreate(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    provider: Provider
    scenario_id: str | None = Field(default=None, max_length=100)
    resource_id: str | None = Field(default=None, max_length=200)
    time_window: TimeWindow | None = None


class ToolStep(BaseModel):
    index: int
    tool: str
    status: Literal["running", "completed", "failed"]
    input: dict[str, Any]
    output_summary: str | None = None
    started_at: datetime
    duration_ms: int | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    error: str | None = None


class Evidence(BaseModel):
    id: str
    type: EvidenceType
    source_tool: str
    title: str
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)
    simulated: bool = False


class ObservedFact(BaseModel):
    statement: str
    evidence_ids: list[str] = Field(default_factory=list)


class PossibleCause(BaseModel):
    cause: str
    likelihood: Likelihood
    rationale: str
    evidence_ids: list[str] = Field(default_factory=list)


class Recommendation(BaseModel):
    action: str
    risk: Risk
    rationale: str


class Report(BaseModel):
    summary: str
    severity_assessment: Severity
    observed_facts: list[ObservedFact]
    possible_causes: list[PossibleCause]
    recommendations: list[Recommendation]
    confidence: Confidence
    limitations: list[str]
    llm_provider: str


class Investigation(BaseModel):
    id: str
    question: str
    provider: Provider
    resource_id: str | None
    scenario_id: str | None
    status: InvestigationStatus
    created_at: datetime
    completed_at: datetime | None = None
    time_window: TimeWindow | None = None
    steps: list[ToolStep] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    report: Report | None = None
    error: str | None = None
    simulated: bool = False


class InvestigationSummary(BaseModel):
    id: str
    question: str
    provider: Provider
    resource_id: str | None
    scenario_id: str | None
    status: InvestigationStatus
    severity_assessment: Severity | None = None
    created_at: datetime
    completed_at: datetime | None = None
    step_count: int = 0
    simulated: bool = False


class InvestigationListResponse(BaseModel):
    items: list[InvestigationSummary]
    total: int
    page: int
    page_size: int


class HealthResponse(BaseModel):
    status: str
    version: str
    time: datetime


OverviewResponse.model_rebuild()
