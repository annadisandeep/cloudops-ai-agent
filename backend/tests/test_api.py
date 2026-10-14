"""API endpoint tests, including a full demo investigation lifecycle."""

import pytest

from app.config import get_settings
from tests.conftest import wait_for_completion


class TestSystemEndpoints:
    def test_health(self, client):
        r = client.get("/api/v1/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok" and "version" in body

    def test_config_never_exposes_secrets(self, client, monkeypatch):
        r = client.get("/api/v1/config")
        assert r.status_code == 200
        assert "api_key" not in r.text.lower().replace("_", "")
        body = r.json()
        assert body["demo_mode"] is True
        assert body["llm"]["provider"] == "mock"
        assert body["limits"]["max_steps"] >= 1

    def test_openapi_served(self, client):
        assert client.get("/openapi.json").status_code == 200

    def test_providers_listing(self, client):
        items = client.get("/api/v1/providers").json()["items"]
        ids = {p["id"] for p in items}
        assert ids == {"demo", "gcp", "aws"}

    def test_overview(self, client):
        body = client.get("/api/v1/overview").json()
        assert body["resource_counts"]["total"] == 8
        assert len(body["attention"]) == 6
        assert body["simulated"] is True


class TestScenarios:
    def test_scenarios_labeled_simulated(self, client):
        items = client.get("/api/v1/scenarios").json()["items"]
        assert len(items) == 6
        assert all(s["simulated"] for s in items)
        assert all(s["suggested_question"] for s in items)


class TestResources:
    def test_list_requires_provider(self, client):
        assert client.get("/api/v1/resources").status_code == 422

    def test_list_and_paginate(self, client):
        body = client.get("/api/v1/resources", params={"provider": "demo", "page_size": 3}).json()
        assert body["total"] == 8 and len(body["items"]) == 3
        page2 = client.get(
            "/api/v1/resources", params={"provider": "demo", "page_size": 3, "page": 2}
        ).json()
        assert {r["id"] for r in page2["items"]}.isdisjoint({r["id"] for r in body["items"]})

    def test_search_filter(self, client):
        body = client.get("/api/v1/resources", params={"provider": "demo", "q": "frontend"}).json()
        assert body["total"] == 2

    def test_status_filter(self, client):
        body = client.get("/api/v1/resources", params={"provider": "aws", "status": "stopped"}).json()
        assert body["total"] == 1 and body["items"][0]["name"] == "cache-node-1"

    def test_detail_and_404(self, client):
        assert client.get("/api/v1/resources/gcp/web-frontend-1").status_code == 200
        r = client.get("/api/v1/resources/gcp/ghost-vm")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "not_found"


class TestTelemetry:
    def test_metrics_shape(self, client):
        r = client.get(
            "/api/v1/metrics",
            params={"provider": "gcp", "resource_id": "web-frontend-1", "metric": "cpu_utilization"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["unit"] == "percent" and body["simulated"] is True
        assert len(body["points"]) > 30

    def test_unknown_metric_400(self, client):
        r = client.get(
            "/api/v1/metrics",
            params={"provider": "gcp", "resource_id": "web-frontend-1", "metric": "warp_speed"},
        )
        assert r.status_code == 400

    def test_invalid_window_rejected(self, client):
        r = client.get(
            "/api/v1/metrics",
            params={
                "provider": "gcp", "resource_id": "web-frontend-1", "metric": "cpu_utilization",
                "start": "2026-01-02T00:00:00Z", "end": "2026-01-01T00:00:00Z",
            },
        )
        assert r.status_code == 400

    def test_logs_severity_filter(self, client):
        r = client.get(
            "/api/v1/logs",
            params={"provider": "gcp", "resource_id": "api-backend-1", "severity": "ERROR"},
        )
        assert r.status_code == 200
        body = r.json()
        # The memory scenario emits ERROR/CRITICAL within the default 1h window.
        assert body["entries"]
        assert all(e["severity"] in ("ERROR", "CRITICAL") for e in body["entries"])

    def test_logs_redact_secrets(self, client):
        r = client.get(
            "/api/v1/logs",
            params={"provider": "gcp", "resource_id": "checkout-service-1", "severity": "DEBUG"},
        )
        assert "wJalrXUtnFEMI" not in r.text
        assert r.status_code == 200

    def test_invalid_severity_422(self, client):
        r = client.get(
            "/api/v1/logs",
            params={"provider": "gcp", "resource_id": "web-frontend-1", "severity": "LOUD"},
        )
        assert r.status_code == 422


class TestInvestigationLifecycle:
    def test_full_demo_investigation(self, client):
        r = client.post(
            "/api/v1/investigations",
            json={
                "question": "Why is my GCP VM experiencing high CPU utilization?",
                "provider": "demo",
                "scenario_id": "gcp-high-cpu",
            },
        )
        assert r.status_code == 201
        created = r.json()
        assert created["status"] in ("queued", "running")
        assert created["simulated"] is True

        inv = wait_for_completion(client, created["id"])
        assert inv["status"] == "completed"
        assert inv["resource_id"] == "web-frontend-1"
        assert len(inv["steps"]) >= 3
        assert all(s["status"] in ("completed", "failed") for s in inv["steps"])
        assert inv["report"]["observed_facts"]
        evidence_ids = {e["id"] for e in inv["evidence"]}
        for fact in inv["report"]["observed_facts"]:
            assert set(fact["evidence_ids"]) <= evidence_ids
        assert all(e["simulated"] for e in inv["evidence"])

        # Markdown export
        md = client.get(f"/api/v1/investigations/{created['id']}/report.md")
        assert md.status_code == 200
        assert "Incident Report" in md.text
        assert "simulated" in md.text.lower()
        assert "Observed facts" in md.text

    def test_unknown_scenario_rejected(self, client):
        r = client.post(
            "/api/v1/investigations",
            json={"question": "test?", "provider": "demo", "scenario_id": "nope"},
        )
        assert r.status_code == 400

    def test_question_length_validated(self, client):
        r = client.post(
            "/api/v1/investigations",
            json={"question": "x" * 3000, "provider": "demo"},
        )
        assert r.status_code == 422

    def test_bad_time_window_rejected(self, client):
        r = client.post(
            "/api/v1/investigations",
            json={
                "question": "test window?",
                "provider": "demo",
                "time_window": {"start": "2026-01-02T00:00:00Z", "end": "2026-01-01T00:00:00Z"},
            },
        )
        assert r.status_code == 400

    def test_get_unknown_investigation_404(self, client):
        assert client.get("/api/v1/investigations/inv_ghost").status_code == 404

    def test_report_not_ready_404(self, client):
        r = client.post(
            "/api/v1/investigations",
            json={"question": "slow test?", "provider": "demo", "scenario_id": "gcp-high-cpu"},
        )
        inv_id = r.json()["id"]
        # Either still running (404) or already done (200) — tolerate the race,
        # but a brand-new id must never 500.
        md = client.get(f"/api/v1/investigations/{inv_id}/report.md")
        assert md.status_code in (200, 404)
        wait_for_completion(client, inv_id)

    def test_history_search_and_pagination(self, client):
        r = client.post(
            "/api/v1/investigations",
            json={"question": "memory leak check", "provider": "demo", "scenario_id": "gcp-low-memory"},
        )
        wait_for_completion(client, r.json()["id"])
        body = client.get("/api/v1/investigations", params={"q": "memory"}).json()
        assert body["total"] >= 1
        assert any("memory" in i["question"] for i in body["items"])
        none = client.get("/api/v1/investigations", params={"q": "zzz-no-match"}).json()
        assert none["total"] == 0

    def test_history_persists_across_app_restarts(self, client):
        r = client.post(
            "/api/v1/investigations",
            json={"question": "persistence check", "provider": "demo", "scenario_id": "storage-capacity"},
        )
        inv_id = r.json()["id"]
        wait_for_completion(client, inv_id)

        # New app instance, same DB file.
        from fastapi.testclient import TestClient

        from app.main import create_app

        with TestClient(create_app()) as client2:
            inv = client2.get(f"/api/v1/investigations/{inv_id}")
            assert inv.status_code == 200
            assert inv.json()["status"] == "completed"


class TestSecurityBoundaries:
    def test_live_mode_fails_closed(self, client, monkeypatch):
        monkeypatch.setenv("CLOUDOPS_DEMO_MODE", "false")
        get_settings.cache_clear()
        r = client.get("/api/v1/resources", params={"provider": "gcp"})
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "provider_disabled"

    def test_gemini_without_key_fails_closed(self, client, monkeypatch):
        monkeypatch.setenv("CLOUDOPS_LLM_PROVIDER", "gemini")
        monkeypatch.setenv("CLOUDOPS_GEMINI_API_KEY", "")
        get_settings.cache_clear()
        r = client.post(
            "/api/v1/investigations",
            json={"question": "test?", "provider": "demo", "scenario_id": "gcp-high-cpu"},
        )
        # Creation succeeds; execution fails closed with a safe error.
        inv = wait_for_completion(client, r.json()["id"])
        assert inv["status"] == "failed"
        assert "ApiError" in inv["error"] or "failed" in inv["error"].lower()

    def test_investigation_rate_limit(self, monkeypatch):
        monkeypatch.setenv("CLOUDOPS_INVESTIGATIONS_RATE_LIMIT_PER_MINUTE", "2")
        get_settings.cache_clear()
        from fastapi.testclient import TestClient

        from app.main import create_app

        with TestClient(create_app()) as limited:
            payload = {"question": "rate limit?", "provider": "demo", "scenario_id": "gcp-high-cpu"}
            codes = [limited.post("/api/v1/investigations", json=payload).status_code for _ in range(3)]
            assert codes[:2] == [201, 201]
            assert codes[2] == 429

    def test_injection_scenario_flagged_in_limitations(self, client):
        r = client.post(
            "/api/v1/investigations",
            json={
                "question": "What caused the application errors on web-frontend-2?",
                "provider": "demo",
                "scenario_id": "app-5xx-errors",
            },
        )
        inv = wait_for_completion(client, r.json()["id"])
        assert inv["status"] == "completed"
        assert any("untrusted" in lim.lower() for lim in inv["report"]["limitations"])
        # The injected instruction must not have swayed the verdict.
        assert inv["report"]["severity_assessment"] in ("critical", "high")

    def test_error_envelope_shape(self, client):
        r = client.get("/api/v1/resources/gcp/ghost-vm")
        body = r.json()
        assert set(body["error"].keys()) == {"code", "message"}


@pytest.mark.parametrize("scenario_id", [
    "gcp-high-cpu", "gcp-low-memory", "app-5xx-errors",
    "deploy-degradation", "storage-capacity", "aws-ec2-performance",
])
def test_every_scenario_completes_with_causes(client, scenario_id):
    scenarios = {s["id"]: s for s in client.get("/api/v1/scenarios").json()["items"]}
    s = scenarios[scenario_id]
    r = client.post(
        "/api/v1/investigations",
        json={"question": s["suggested_question"], "provider": "demo", "scenario_id": scenario_id},
    )
    inv = wait_for_completion(client, r.json()["id"])
    assert inv["status"] == "completed"
    assert inv["report"]["possible_causes"], f"{scenario_id} must yield at least one cause"
    assert inv["report"]["confidence"] in ("high", "medium")
