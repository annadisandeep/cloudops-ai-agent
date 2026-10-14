"""LangGraph workflow: transitions, bounds, resource resolution, evidence attribution."""

from datetime import UTC, datetime, timedelta

from app.agent.graph import run_investigation_graph
from app.agent.planner import MockPlanner, PlannerDecision
from app.agent.tools import ToolExecutor
from app.providers.demo import DemoAdapter
from app.schemas import Report, TimeWindow


def make_state(question: str, resource_id: str | None, max_steps: int = 8) -> dict:
    end = datetime.now(UTC)
    return {
        "investigation_id": "inv_test",
        "question": question,
        "provider": "demo",
        "scenario_id": None,
        "resource_id": resource_id,
        "time_window": {"start": (end - timedelta(minutes=90)).isoformat(), "end": end.isoformat()},
        "max_steps": max_steps,
        "steps": [],
        "evidence": [],
        "step_count": 0,
        "failed_tool_calls": 0,
        "report": None,
        "error": None,
    }


def run(question: str, resource_id: str | None, max_steps: int = 8, planner=None):
    end = datetime.now(UTC)
    window = TimeWindow(start=end - timedelta(minutes=90), end=end)
    executor = ToolExecutor(DemoAdapter(), window, "inv_test")
    planner = planner or MockPlanner()
    return run_investigation_graph(
        planner, executor, make_state(question, resource_id, max_steps), simulated=True
    )


def test_full_investigation_produces_grounded_report():
    final = run("Why is web-frontend-1 CPU so high?", "web-frontend-1")
    assert final["report"] is not None
    report = Report.model_validate(final["report"])
    assert report.observed_facts, "expected grounded facts"
    evidence_ids = {e["id"] for e in final["evidence"]}
    for fact in report.observed_facts:
        assert fact.evidence_ids, "every fact must cite evidence"
        assert set(fact.evidence_ids) <= evidence_ids, "facts must cite real evidence"
    assert report.severity_assessment == "high"
    tools_used = [s["tool"] for s in final["steps"]]
    assert "get_resource_metadata" in tools_used
    assert "get_metrics" in tools_used
    assert "query_logs" in tools_used


def test_step_limit_enforced():
    final = run("Why is web-frontend-1 CPU so high?", "web-frontend-1", max_steps=2)
    assert len(final["steps"]) == 2
    assert final["report"] is not None, "analysis must still run at the limit"


def test_resource_resolved_from_question_via_inventory():
    final = run("Summarize the incident on batch-worker-1 please", None)
    assert final["resource_id"] == "i-0f1e2d3c4b5a69788"
    assert final["steps"][0]["tool"] == "list_resources"


def test_unresolvable_resource_finishes_with_low_confidence():
    final = run("What is the meaning of life?", None)
    report = Report.model_validate(final["report"])
    assert final["resource_id"] is None
    assert report.confidence == "low"
    assert not report.possible_causes
    summary = report.summary.lower()
    assert "insufficient" in summary or "no root cause" in summary


def test_failed_call_budget_short_circuits():
    class BrokenAdapter(DemoAdapter):
        def get_resource(self, resource_id):
            raise ConnectionError("down")

        def get_metrics(self, *a, **k):
            raise ConnectionError("down")

        def query_logs(self, *a, **k):
            raise ConnectionError("down")

    end = datetime.now(UTC)
    window = TimeWindow(start=end - timedelta(minutes=90), end=end)
    executor = ToolExecutor(BrokenAdapter(), window, "inv_test")
    final = run_investigation_graph(
        MockPlanner(), executor, make_state("cpu high on web-frontend-1", "web-frontend-1"), simulated=True
    )
    assert final["failed_tool_calls"] >= 3
    assert len(final["steps"]) <= 5
    assert final["report"] is not None
    report = Report.model_validate(final["report"])
    assert report.confidence == "low"
    assert any("failed" in lim for lim in report.limitations)


def test_planner_crash_still_produces_fallback_report():
    class CrashyPlanner(MockPlanner):
        def write_report(self, state, simulated):
            raise RuntimeError("llm exploded")

    final = run("Why is web-frontend-1 CPU high?", "web-frontend-1", planner=CrashyPlanner())
    assert final["report"] is not None
    report = Report.model_validate(final["report"])
    assert any("deterministic analyzer" in lim for lim in report.limitations)


def test_disallowed_planner_tool_never_executes():
    class EvilPlanner(MockPlanner):
        def __init__(self):
            super().__init__()
            self.asked = False

        def decide(self, state) -> PlannerDecision:
            if not self.asked:
                self.asked = True
                return PlannerDecision(action="call_tool", tool="delete_instance", args={"id": "x"})
            return PlannerDecision(action="finish")

    final = run("delete something", "web-frontend-1", planner=EvilPlanner())
    failed = [s for s in final["steps"] if s["status"] == "failed"]
    assert failed and "allowlist" in failed[0]["error"]


def test_scenario_key_metrics_drive_tool_selection():
    planner = MockPlanner(scenario_key_metrics=["disk_used_percent", "network_in_bytes"])
    final = run("storage issue?", "data-warehouse-1", planner=planner)
    metrics = [s["input"].get("metric") for s in final["steps"] if s["tool"] == "get_metrics"]
    assert metrics[:2] == ["disk_used_percent", "network_in_bytes"]
