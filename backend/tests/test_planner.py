"""Planner behavior: mock keyword routing, Gemini fail-closed and guardrails."""

import pytest

from app.agent.planner import GeminiPlanner, MockPlanner, PlannerDecision, get_planner
from app.config import get_settings
from app.errors import ApiError


class TestMockPlanner:
    def test_keyword_metric_selection(self):
        p = MockPlanner()
        assert p._select_metrics("why is memory low?")[0] == "memory_available_mb"
        assert p._select_metrics("too many 5xx errors")[0] == "http_5xx_count"
        assert p._select_metrics("disk almost full")[0] == "disk_used_percent"
        assert p._select_metrics("something odd")[0] == "cpu_utilization"

    def test_scenario_metrics_override_keywords(self):
        p = MockPlanner(scenario_key_metrics=["latency_ms_p95"])
        assert p._select_metrics("memory problem?") == ["latency_ms_p95"]

    def test_first_decision_without_resource_lists_inventory(self):
        p = MockPlanner()
        d = p.decide({"question": "what is broken?", "steps": [], "evidence": []})
        assert d.action == "call_tool" and d.tool == "list_resources"

    def test_decision_with_resource_fetches_metadata_first(self):
        p = MockPlanner()
        d = p.decide({"question": "cpu?", "resource_id": "web-frontend-1", "steps": [], "evidence": []})
        assert d.tool == "get_resource_metadata"


class TestGeminiPlanner:
    def test_fails_closed_without_api_key(self, monkeypatch):
        monkeypatch.setenv("CLOUDOPS_LLM_PROVIDER", "gemini")
        monkeypatch.setenv("CLOUDOPS_GEMINI_API_KEY", "")
        get_settings.cache_clear()
        with pytest.raises(ApiError) as exc:
            get_planner()
        assert exc.value.code == "llm_unconfigured"

    def test_disallowed_tool_from_llm_is_never_executed(self, monkeypatch):
        monkeypatch.setenv("CLOUDOPS_LLM_PROVIDER", "gemini")
        monkeypatch.setenv("CLOUDOPS_GEMINI_API_KEY", "test-key-not-real")
        get_settings.cache_clear()
        planner = GeminiPlanner.__new__(GeminiPlanner)  # skip client construction
        planner._model = "test"

        def fake_generate(prompt, schema):
            return PlannerDecision(action="call_tool", tool="delete_all_instances", args={})

        planner._generate = fake_generate  # type: ignore[method-assign]
        decision = planner.decide({
            "question": "q", "provider": "demo", "resource_id": "x",
            "time_window": {}, "step_count": 0, "max_steps": 8, "steps": [], "evidence": [],
        })
        assert decision.action == "finish"

    def test_report_evidence_ids_are_validated(self, monkeypatch):
        from app.schemas import ObservedFact, Report

        planner = GeminiPlanner.__new__(GeminiPlanner)
        planner._model = "test"

        fake_report = Report(
            summary="s", severity_assessment="low",
            observed_facts=[ObservedFact(statement="made up", evidence_ids=["ev_999"])],
            possible_causes=[], recommendations=[], confidence="low",
            limitations=[], llm_provider="gemini",
        )
        planner._generate = lambda prompt, schema: fake_report  # type: ignore[method-assign]
        report = planner.write_report(
            {"question": "q", "steps": [], "evidence": [{"id": "ev_1", "type": "metric",
             "source_tool": "get_metrics", "title": "t", "summary": "s", "data": {}}]},
            simulated=True,
        )
        assert report.observed_facts[0].evidence_ids == [], "fabricated evidence ids must be stripped"
