"""Explicit agent state for the LangGraph investigation workflow."""

from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    # Immutable context
    investigation_id: str
    question: str
    provider: str
    scenario_id: str | None
    time_window: dict[str, str]  # {"start": iso, "end": iso}
    max_steps: int

    # Mutable working state
    resource_id: str | None
    decision: dict[str, Any] | None  # planner output: {action, tool, args, reasoning}
    steps: list[dict[str, Any]]  # serialized ToolStep
    evidence: list[dict[str, Any]]  # serialized Evidence
    step_count: int
    failed_tool_calls: int

    # Terminal outputs
    report: dict[str, Any] | None
    error: str | None
