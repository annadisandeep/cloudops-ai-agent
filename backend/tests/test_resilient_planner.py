"""Resilient fallback: Gemini runtime failures must not end evidence collection,
and the final report must honestly attribute which engine produced it."""

from datetime import UTC, datetime, timedelta

from app.agent.graph import run_investigation_graph
from app.agent.planner import (
    MockPlanner,
    PlannerDecision,
    ResilientPlanner,
    categorize_llm_error,
)
from app.agent.tools import ToolExecutor
from app.errors import ApiError
from app.providers.demo import DemoAdapter
from app.schemas import Report, TimeWindow


class FakeServerError(Exception):
    """Mimics google.genai.errors.ServerError (categorized by class name)."""


FakeServerError.__name__ = "ServerError"


class FailingPrimary:
    """Primary planner that fails after N successful decisions."""

    name = "gemini"

    def __init__(self, succeed_decides: int = 0, decide_exc=None, report_exc=None):
        self._succeed = succeed_decides
        self._decide_exc = decide_exc or FakeServerError("500 INTERNAL from API")
        self._report_exc = report_exc or FakeServerError("500 INTERNAL from API")
        self._mock = MockPlanner()
        self.decides = 0

    def decide(self, state):
        self.decides += 1
        if self.decides > self._succeed:
            raise self._decide_exc
        return self._mock.decide(state)

    def write_report(self, state, simulated):
        raise self._report_exc


class WorkingPrimary:
    name = "gemini"

    def __init__(self):
        self._mock = MockPlanner()

    def decide(self, state):
        return self._mock.decide(state)

    def write_report(self, state, simulated):
        report = self._mock.write_report(state, simulated)
        report.llm_provider = "placeholder"
        return report


def run_graph(planner):
    end = datetime.now(UTC)
    window = TimeWindow(start=end - timedelta(minutes=90), end=end)
    executor = ToolExecutor(DemoAdapter(), window, "inv_test")
    state = {
        "investigation_id": "inv_test",
        "question": "Why is web-frontend-1 CPU so high?",
        "provider": "demo",
        "scenario_id": None,
        "resource_id": "web-frontend-1",
        "time_window": {"start": window.start.isoformat(), "end": window.end.isoformat()},
        "max_steps": 8,
        "steps": [],
        "evidence": [],
        "step_count": 0,
        "failed_tool_calls": 0,
        "report": None,
        "error": None,
    }
    return run_investigation_graph(planner, executor, state, simulated=True)


def test_decide_failure_before_first_tool_still_collects_evidence():
    """Regression for the observed incident: Gemini fails on the very first
    planning call -> previously 0 tool calls / 0 evidence. Now the deterministic
    fallback must run the full evidence collection."""
    planner = ResilientPlanner(FailingPrimary(succeed_decides=0), MockPlanner())
    final = run_graph(planner)

    assert len(final["steps"]) >= 3, "fallback must collect real tool evidence"
    assert len(final["evidence"]) >= 3
    assert planner.degraded and planner.failure_stage == "planning"
    assert planner.failed_at_step == 0
    report = Report.model_validate(final["report"])
    assert report.observed_facts, "report must be grounded in collected evidence"
    assert report.llm_provider == "mock", "fallback report must not claim Gemini authorship"
    assert any("deterministic" in lim.lower() for lim in report.limitations)
    assert any("api_server_error" in lim for lim in report.limitations)


def test_midstream_decide_failure_continues_collection():
    planner = ResilientPlanner(FailingPrimary(succeed_decides=2), MockPlanner())
    final = run_graph(planner)

    assert planner.degraded and planner.failed_at_step == 2
    # Evidence collection continued past the failure point within limits.
    assert len(final["steps"]) > 2
    assert len(final["steps"]) <= 8
    report = Report.model_validate(final["report"])
    assert report.llm_provider == "mock"


def test_report_writer_failure_falls_back_with_honest_attribution():
    """Primary plans fine but the report writer fails -> deterministic report,
    attributed to mock, with a categorized limitation naming the report stage."""
    planner = ResilientPlanner(
        FailingPrimary(succeed_decides=99), MockPlanner()
    )
    final = run_graph(planner)

    assert planner.degraded and planner.failure_stage == "report"
    report = Report.model_validate(final["report"])
    assert report.llm_provider == "mock"
    assert report.observed_facts, "evidence collected by the primary is still analyzed"
    assert any("during report" in lim for lim in report.limitations)


def test_successful_primary_is_attributed_to_gemini():
    planner = ResilientPlanner(WorkingPrimary(), MockPlanner())
    final = run_graph(planner)

    assert not planner.degraded
    report = Report.model_validate(final["report"])
    assert report.llm_provider == "gemini", "wrapper must attribute the actual engine"
    assert not any("deterministic planner/analyzer completed" in lim for lim in report.limitations)


def test_no_secret_leakage_in_fallback_limitation(caplog):
    """Exception text containing credential material must be redacted in the
    report limitation and in logs."""
    import logging

    sentinel = "SENTINEL9876543210abcdef"
    exc = FakeServerError(f"500 INTERNAL; request used api_key={sentinel} and failed")
    planner = ResilientPlanner(FailingPrimary(decide_exc=exc, report_exc=exc), MockPlanner())
    with caplog.at_level(logging.DEBUG):
        final = run_graph(planner)

    report = Report.model_validate(final["report"])
    joined = " ".join(report.limitations)
    assert sentinel not in joined, "key material leaked into report limitations"
    assert "[REDACTED]" in joined
    assert sentinel not in caplog.text, "key material leaked into logs"


class TestErrorCategorization:
    def _named(self, name: str, message: str = "boom", code=None):
        exc_type = type(name, (Exception,), {})
        exc = exc_type(message)
        if code is not None:
            exc.code = code
        return exc

    def test_server_error(self):
        cat, _ = categorize_llm_error(self._named("ServerError", "500 INTERNAL"))
        assert cat == "api_server_error"

    def test_model_not_found(self):
        cat, _ = categorize_llm_error(
            self._named("ClientError", "404 NOT_FOUND: model gemini-x is not found", code=404)
        )
        assert cat == "model_unavailable"

    def test_quota(self):
        cat, _ = categorize_llm_error(
            self._named("ClientError", "429 RESOURCE_EXHAUSTED: quota exceeded", code=429)
        )
        assert cat == "quota_exhausted"

    def test_invalid_argument(self):
        cat, _ = categorize_llm_error(
            self._named("ClientError", "400 INVALID_ARGUMENT: response_schema", code=400)
        )
        assert cat == "invalid_request"

    def test_auth(self):
        cat, _ = categorize_llm_error(
            self._named("ClientError", "403 PERMISSION_DENIED: API key not valid", code=403)
        )
        assert cat == "auth_error"

    def test_malformed_structured_output(self):
        cat, _ = categorize_llm_error(
            ApiError("llm_invalid_output", "schema validation failed", 502)
        )
        assert cat == "malformed_structured_output"

    def test_transient_network(self):
        cat, _ = categorize_llm_error(ConnectionError("reset"))
        assert cat == "transient_network"

    def test_unknown(self):
        cat, _ = categorize_llm_error(RuntimeError("weird"))
        assert cat == "unknown"

    def test_message_is_redacted_and_bounded(self):
        cat, detail = categorize_llm_error(
            self._named("ServerError", "boom token=supersecretvalue123 " + "x" * 1000)
        )
        assert "supersecretvalue123" not in detail
        assert len(detail) <= 300


class TestGeminiDecisionParsing:
    """Gemini-facing args_json parsing (open dicts are unsupported by the
    structured-output API, so arguments travel as a JSON string)."""

    def _planner(self):
        from app.agent.planner import GeminiPlanner

        planner = GeminiPlanner.__new__(GeminiPlanner)
        planner._model = "test"
        return planner

    def _state(self):
        return {
            "question": "q", "provider": "demo", "resource_id": "x",
            "time_window": {}, "step_count": 0, "max_steps": 8, "steps": [], "evidence": [],
        }

    def test_valid_args_json_parsed(self):
        from app.agent.planner import _GeminiDecision

        planner = self._planner()
        planner._generate = lambda prompt, schema: _GeminiDecision(
            action="call_tool", tool="get_metrics",
            args_json='{"resource_id": "web-frontend-1", "metric": "cpu_utilization"}',
        )
        decision = planner.decide(self._state())
        assert isinstance(decision, PlannerDecision)
        assert decision.args == {"resource_id": "web-frontend-1", "metric": "cpu_utilization"}

    def test_malformed_args_json_raises_invalid_output(self):
        import pytest

        from app.agent.planner import _GeminiDecision

        planner = self._planner()
        planner._generate = lambda prompt, schema: _GeminiDecision(
            action="call_tool", tool="get_metrics", args_json="{not json"
        )
        with pytest.raises(ApiError) as exc:
            planner.decide(self._state())
        assert exc.value.code == "llm_invalid_output"

    def test_non_object_args_json_rejected(self):
        import pytest

        from app.agent.planner import _GeminiDecision

        planner = self._planner()
        planner._generate = lambda prompt, schema: _GeminiDecision(
            action="call_tool", tool="get_metrics", args_json='["not", "a", "dict"]'
        )
        with pytest.raises(ApiError):
            planner.decide(self._state())
