"""Investigation lifecycle: create record, run the graph in a worker thread,
persist progress incrementally, enforce the overall timeout."""

from __future__ import annotations

import logging
import secrets
import threading
from datetime import UTC, datetime, timedelta

from .. import db
from ..config import get_settings
from ..demo.data import SCENARIO_INDEX, scenario_window
from ..errors import ValidationApiError
from ..providers.registry import get_adapter
from ..schemas import Investigation, InvestigationCreate, TimeWindow
from .graph import run_investigation_graph
from .planner import get_planner
from .state import AgentState
from .tools import ToolExecutor

logger = logging.getLogger("cloudops.agent.runner")


def new_investigation_id() -> str:
    return f"inv_{secrets.token_hex(4)}"


def prepare_investigation(payload: InvestigationCreate) -> Investigation:
    """Validate the request, resolve scenario/resource/time window, persist the
    queued record. Raises ApiError subclasses on invalid input."""
    settings = get_settings()
    scenario = None
    if payload.scenario_id:
        scenario = SCENARIO_INDEX.get(payload.scenario_id)
        if scenario is None:
            raise ValidationApiError(f"Unknown scenario '{payload.scenario_id}'")
        if not settings.demo_mode:
            raise ValidationApiError("Scenarios are only available in demo mode.")

    resource_id = payload.resource_id or (scenario.resource_id if scenario else None)

    if payload.time_window:
        window = payload.time_window
        if window.end <= window.start:
            raise ValidationApiError("time_window.end must be after time_window.start")
        if window.end - window.start > timedelta(days=7):
            raise ValidationApiError("time_window must be 7 days or shorter")
    else:
        start, end = scenario_window()
        window = TimeWindow(start=start, end=end)

    adapter = get_adapter(payload.provider)  # fails closed if provider disabled

    inv = Investigation(
        id=new_investigation_id(),
        question=payload.question,
        provider=payload.provider,
        resource_id=resource_id,
        scenario_id=payload.scenario_id,
        status="queued",
        created_at=datetime.now(UTC),
        time_window=window,
        simulated=adapter.simulated,
    )
    db.save_investigation(inv)
    return inv


def _persist_state(inv: Investigation, state: AgentState) -> None:
    inv.resource_id = state.get("resource_id") or inv.resource_id
    inv.steps = state.get("steps", [])  # type: ignore[assignment]
    inv.evidence = state.get("evidence", [])  # type: ignore[assignment]
    db.save_investigation(inv)


def execute_investigation(inv_id: str) -> None:
    """Runs synchronously (call from a worker thread)."""
    inv = db.get_investigation(inv_id)
    if inv is None:
        logger.error("Investigation %s disappeared before execution", inv_id)
        return
    settings = get_settings()
    inv.status = "running"
    db.save_investigation(inv)

    try:
        adapter = get_adapter(inv.provider)
        scenario = SCENARIO_INDEX.get(inv.scenario_id) if inv.scenario_id else None
        planner = get_planner(scenario.key_metrics if scenario else None)
        assert inv.time_window is not None
        executor = ToolExecutor(adapter, inv.time_window, inv.id)

        initial: AgentState = {
            "investigation_id": inv.id,
            "question": inv.question,
            "provider": inv.provider,
            "scenario_id": inv.scenario_id,
            "resource_id": inv.resource_id,
            "time_window": {
                "start": inv.time_window.start.isoformat(),
                "end": inv.time_window.end.isoformat(),
            },
            "max_steps": settings.max_steps,
            "steps": [],
            "evidence": [],
            "step_count": 0,
            "failed_tool_calls": 0,
            "report": None,
            "error": None,
        }

        deadline = datetime.now(UTC) + timedelta(
            seconds=settings.investigation_timeout_seconds
        )

        def persist(state: AgentState) -> None:
            if datetime.now(UTC) > deadline:
                raise TimeoutError("Investigation exceeded the configured timeout")
            _persist_state(inv, state)

        final = run_investigation_graph(planner, executor, initial, adapter.simulated, persist)

        inv.resource_id = final.get("resource_id") or inv.resource_id
        inv.steps = final.get("steps", [])  # type: ignore[assignment]
        inv.evidence = final.get("evidence", [])  # type: ignore[assignment]
        if final.get("report"):
            from ..schemas import Report

            inv.report = Report.model_validate(final["report"])
        inv.status = "completed"
        inv.completed_at = datetime.now(UTC)
        db.save_investigation(inv)
        logger.info("Investigation %s completed with %d steps", inv.id, len(inv.steps))
    except TimeoutError:
        inv.status = "failed"
        inv.error = f"Investigation timed out after {settings.investigation_timeout_seconds}s."
        inv.completed_at = datetime.now(UTC)
        db.save_investigation(inv)
    except Exception as exc:
        logger.exception("Investigation %s failed", inv_id)
        inv.status = "failed"
        inv.error = f"Investigation failed: {type(exc).__name__}"
        inv.completed_at = datetime.now(UTC)
        db.save_investigation(inv)


def start_investigation_async(inv_id: str) -> None:
    thread = threading.Thread(
        target=execute_investigation, args=(inv_id,), name=f"investigation-{inv_id}", daemon=True
    )
    thread.start()
