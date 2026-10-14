"""Gemini tool-argument reliability.

Root cause regression: Gemini supplied start_time/end_time instead of the exact
schema names start/end, so get_metrics and query_logs failed with
"Extra inputs are not permitted". The planner prompt now carries exact,
schema-derived signatures; rejected calls name the offending and allowed fields
(never silently discarded); malformed arguments stay bounded by the
failed-call budget.
"""

from datetime import UTC, datetime, timedelta

from app.agent.graph import MAX_FAILED_CALLS, run_investigation_graph
from app.agent.planner import GeminiPlanner, MockPlanner, PlannerDecision, _GeminiDecision
from app.agent.tools import ToolExecutor, tool_argument_spec
from app.providers.demo import DemoAdapter
from app.schemas import Report, TimeWindow


def make_executor():
    end = datetime.now(UTC)
    window = TimeWindow(start=end - timedelta(hours=2), end=end)
    return ToolExecutor(DemoAdapter(), window, "inv_test")


class TestArgumentSpec:
    def test_spec_is_generated_from_schemas(self):
        spec = tool_argument_spec()
        assert "get_metrics(resource_id (required), metric (required), start (optional), " in spec
        assert "query_logs(resource_id (required), start (optional), end (optional), " in spec
        assert "list_resources(no arguments)" in spec
        assert "start_time" not in spec

    def test_gemini_prompt_contains_exact_signatures(self):
        planner = GeminiPlanner.__new__(GeminiPlanner)
        planner._model = "test"
        captured = {}

        def fake_generate(prompt, schema):
            captured["prompt"] = prompt
            return _GeminiDecision(action="finish", reasoning="done")

        planner._generate = fake_generate  # type: ignore[method-assign]
        planner.decide({
            "question": "q", "provider": "demo", "resource_id": "x",
            "time_window": {}, "step_count": 0, "max_steps": 8, "steps": [], "evidence": [],
        })
        prompt = captured["prompt"]
        assert "ONLY these argument names" in prompt
        assert "never start_time/end_time" in prompt
        assert tool_argument_spec() in prompt


class TestObservedFailureRegression:
    """The exact argument sets Gemini produced in the failed live investigations."""

    def test_get_metrics_with_start_time_end_time_rejected_with_guidance(self):
        executor = make_executor()
        step, evidence = executor.execute(
            "get_metrics",
            {
                "resource_id": "web-frontend-1",
                "metric": "cpu_utilization",
                "start_time": "2026-10-14T14:22:00+00:00",
                "end_time": "2026-10-14T15:52:00+00:00",
            },
            0,
        )
        assert step.status == "failed" and evidence == []
        assert "unexpected field(s): end_time, start_time" in step.error
        assert "Allowed fields for get_metrics: resource_id, metric, start, end, step_seconds" in step.error

    def test_query_logs_with_start_time_end_time_rejected_with_guidance(self):
        executor = make_executor()
        step, _ = executor.execute(
            "query_logs",
            {
                "resource_id": "web-frontend-1",
                "start_time": "2026-10-14T14:22:00+00:00",
                "end_time": "2026-10-14T15:52:00+00:00",
                "min_severity": "INFO",
            },
            0,
        )
        assert step.status == "failed"
        assert "unexpected field(s): end_time, start_time" in step.error
        assert "Allowed fields for query_logs:" in step.error

    def test_corrected_gemini_args_succeed(self):
        """The same calls with the exact field names (ISO strings) must work —
        Gemini sends strings, Pydantic coerces to datetimes."""
        executor = make_executor()
        end = datetime.now(UTC)
        start = end - timedelta(minutes=90)
        step_m, ev_m = executor.execute(
            "get_metrics",
            {
                "resource_id": "web-frontend-1",
                "metric": "cpu_utilization",
                "start": start.isoformat(),
                "end": end.isoformat(),
            },
            0,
        )
        assert step_m.status == "completed" and ev_m[0].data["stats"]["count"] > 0
        step_l, ev_l = executor.execute(
            "query_logs",
            {
                "resource_id": "web-frontend-1",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "min_severity": "INFO",
            },
            1,
        )
        assert step_l.status == "completed" and ev_l[0].type == "log"

    def test_mixed_valid_and_invalid_fields_rejects_whole_call(self):
        """Unknown args must never be silently dropped to salvage the call."""
        executor = make_executor()
        step, evidence = executor.execute(
            "get_metrics",
            {"resource_id": "web-frontend-1", "metric": "cpu_utilization", "window": "1h"},
            0,
        )
        assert step.status == "failed", "call with unknown fields must fail, not be cleaned"
        assert evidence == []
        assert "unexpected field(s): window" in step.error


class BadArgsPlanner:
    """Simulates an LLM that keeps producing wrong argument names."""

    name = "gemini"

    def decide(self, state):
        return PlannerDecision(
            action="call_tool",
            tool="get_metrics",
            args={"resource_id": "web-frontend-1", "metric": "cpu_utilization",
                  "start_time": "2026-10-14T00:00:00Z"},
            reasoning="wrong field names every time",
        )

    def write_report(self, state, simulated):
        return MockPlanner().write_report(state, simulated)


def test_persistent_bad_args_bounded_by_failed_call_budget():
    """Malformed arguments must not consume excessive steps: the failed-call
    budget short-circuits to analysis well before max_steps."""
    end = datetime.now(UTC)
    window = TimeWindow(start=end - timedelta(minutes=90), end=end)
    executor = ToolExecutor(DemoAdapter(), window, "inv_test")
    state = {
        "investigation_id": "inv_test",
        "question": "cpu?", "provider": "demo", "scenario_id": None,
        "resource_id": "web-frontend-1",
        "time_window": {"start": window.start.isoformat(), "end": window.end.isoformat()},
        "max_steps": 8, "steps": [], "evidence": [], "step_count": 0,
        "failed_tool_calls": 0, "report": None, "error": None,
    }
    final = run_investigation_graph(BadArgsPlanner(), executor, state, simulated=True)

    assert len(final["steps"]) == MAX_FAILED_CALLS, "must stop at the failed-call budget, not max_steps"
    assert all(s["status"] == "failed" for s in final["steps"])
    assert final["report"] is not None, "analysis must still produce a report"
    report = Report.model_validate(final["report"])
    assert report.confidence == "low"
    assert any("failed" in lim for lim in report.limitations)
