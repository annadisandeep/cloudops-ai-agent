"""Demo fixture determinism and shape."""

from datetime import timedelta

from app.demo import data as demo


def test_metric_series_is_deterministic():
    now = demo.anchor_now()
    start, end = now - timedelta(hours=1), now
    a = demo.metric_series("web-frontend-1", "cpu_utilization", start, end, 60, now=now)
    b = demo.metric_series("web-frontend-1", "cpu_utilization", start, end, 60, now=now)
    assert a == b
    assert len(a) == 61


def test_scenario_anomaly_present_in_window():
    now = demo.anchor_now()
    start, end = demo.scenario_window(now)
    series = demo.metric_series("web-frontend-1", "cpu_utilization", start, end, 60, now=now)
    values = [v for _, v in series]
    assert max(values) > 90, "high-CPU scenario must breach 90%"
    # Early window should be near baseline
    assert min(values[:10]) < 50


def test_healthy_resource_stays_baseline():
    now = demo.anchor_now()
    start, end = demo.scenario_window(now)
    series = demo.metric_series("i-0a1b2c3d4e5f60711", "cpu_utilization", start, end, 60, now=now)
    assert max(v for _, v in series) < 60


def test_all_scenarios_reference_existing_resources_and_metrics():
    for s in demo.SCENARIOS:
        assert s.resource_id in demo.RESOURCE_INDEX
        for m in s.key_metrics:
            assert m in demo.METRIC_UNITS
        for m in s.overlays:
            assert m in demo.METRIC_UNITS


def test_six_scenarios_cover_required_categories():
    categories = {s.category for s in demo.SCENARIOS}
    assert {"performance", "memory", "errors", "deployment", "storage"} <= categories
    assert len(demo.SCENARIOS) == 6
    assert any(s.provider == "aws" for s in demo.SCENARIOS)


def test_log_entries_severity_filter_and_limit():
    now = demo.anchor_now()
    start, end = demo.scenario_window(now)
    all_entries, total_all = demo.log_entries("web-frontend-1", start, end, "DEBUG", limit=500, now=now)
    errors, _ = demo.log_entries("web-frontend-1", start, end, "ERROR", limit=500, now=now)
    assert total_all > len(errors) > 0
    assert all(e["severity"] in ("ERROR", "CRITICAL") for e in errors)
    limited, total = demo.log_entries("web-frontend-1", start, end, "DEBUG", limit=3, now=now)
    assert len(limited) == 3 and total == total_all


def test_log_query_substring_filter():
    now = demo.anchor_now()
    start, end = demo.scenario_window(now)
    entries, _ = demo.log_entries("checkout-service-1", start, end, "DEBUG", query="deployment", now=now)
    assert entries and all("deployment" in e["message"].lower() for e in entries)
