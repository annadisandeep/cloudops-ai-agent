"""Persistence roundtrip and markdown report rendering."""

from datetime import UTC, datetime

from app import db
from app.agent.report import render_markdown
from app.schemas import (
    Evidence,
    Investigation,
    ObservedFact,
    PossibleCause,
    Recommendation,
    Report,
    TimeWindow,
    ToolStep,
)


def make_investigation() -> Investigation:
    now = datetime.now(UTC)
    return Investigation(
        id="inv_fixture1",
        question="Why is CPU high?",
        provider="demo",
        resource_id="web-frontend-1",
        scenario_id="gcp-high-cpu",
        status="completed",
        created_at=now,
        completed_at=now,
        time_window=TimeWindow(start=now, end=now),
        steps=[
            ToolStep(index=0, tool="get_metrics", status="completed",
                     input={"metric": "cpu_utilization"}, output_summary="61 points",
                     started_at=now, duration_ms=10, evidence_ids=["ev_1"]),
        ],
        evidence=[
            Evidence(id="ev_1", type="metric", source_tool="get_metrics",
                     title="cpu for web-frontend-1", summary="max 96%", data={"stats": {"max": 96}},
                     simulated=True),
        ],
        report=Report(
            summary="CPU saturated.",
            severity_assessment="high",
            observed_facts=[ObservedFact(statement="CPU peaked at 96%", evidence_ids=["ev_1"])],
            possible_causes=[PossibleCause(cause="Traffic surge", likelihood="likely",
                                           rationale="correlated", evidence_ids=["ev_1"])],
            recommendations=[Recommendation(action="Scale out", risk="low", rationale="adds capacity")],
            confidence="high",
            limitations=["Simulated data"],
            llm_provider="mock",
        ),
        simulated=True,
    )


def test_roundtrip_preserves_everything():
    db.init_db()
    inv = make_investigation()
    db.save_investigation(inv)
    loaded = db.get_investigation("inv_fixture1")
    assert loaded is not None
    assert loaded.question == inv.question
    assert loaded.report is not None and loaded.report.severity_assessment == "high"
    # Pydantic coerces stored dicts back into models on load.
    assert loaded.steps[0].tool == "get_metrics"
    assert loaded.evidence[0].id == "ev_1"
    assert loaded.simulated is True


def test_upsert_updates_status():
    db.init_db()
    inv = make_investigation()
    inv.status = "running"
    db.save_investigation(inv)
    inv.status = "completed"
    db.save_investigation(inv)
    assert db.get_investigation(inv.id).status == "completed"


def test_list_filters():
    db.init_db()
    inv = make_investigation()
    db.save_investigation(inv)
    items, total = db.list_investigations(q="CPU")
    assert total == 1
    items, total = db.list_investigations(status="failed")
    assert total == 0
    items, total = db.list_investigations(provider="demo", page=1, page_size=10)
    assert total == 1 and items[0].step_count == 1


def test_markdown_report_contains_required_sections():
    md = render_markdown(make_investigation())
    for section in (
        "# Incident Report — inv_fixture1",
        "simulated", "Investigation timeline", "Evidence",
        "Observed facts", "Possible causes", "Recommended remediation", "Limitations",
        "`get_metrics`", "CPU peaked at 96%", "Traffic surge", "Scale out",
    ):
        assert section in md, f"missing section: {section}"


def test_markdown_failed_investigation():
    inv = make_investigation()
    inv.status = "failed"
    inv.report = None
    inv.error = "Investigation timed out after 120s."
    md = render_markdown(inv)
    assert "timed out" in md
