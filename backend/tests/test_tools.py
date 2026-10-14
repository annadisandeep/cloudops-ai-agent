"""Tool layer: allowlist, validation, timeout, retries, concurrency, payload bounding."""

from datetime import UTC, datetime, timedelta

import pytest

from app.agent.tools import PENDING_EVIDENCE_ID, WORKER_SLOTS, ToolExecutor
from app.config import get_settings
from app.providers.demo import DemoAdapter
from app.schemas import TimeWindow


@pytest.fixture(autouse=True)
def fresh_worker_slots():
    """Invalidate slots held by stale (still-sleeping) workers from prior tests."""
    WORKER_SLOTS.reset()
    yield
    WORKER_SLOTS.reset()


@pytest.fixture()
def window():
    # Cover the full 90-minute demo scenario window.
    end = datetime.now(UTC)
    return TimeWindow(start=end - timedelta(hours=2), end=end)


@pytest.fixture()
def executor(window):
    return ToolExecutor(DemoAdapter(), window, "inv_test")


def test_disallowed_tool_rejected(executor):
    step, evidence = executor.execute("run_shell_command", {"cmd": "rm -rf /"}, 0)
    assert step.status == "failed"
    assert "allowlist" in (step.error or "")
    assert evidence == []


def test_invalid_args_rejected(executor):
    step, _ = executor.execute("get_metrics", {"resource_id": "web-frontend-1"}, 0)
    assert step.status == "failed"
    assert "Invalid tool arguments" in (step.error or "")


def test_extra_args_rejected(executor):
    step, _ = executor.execute(
        "get_metrics",
        {"resource_id": "web-frontend-1", "metric": "cpu_utilization", "exec": "evil"},
        0,
    )
    assert step.status == "failed"


def test_unknown_resource_not_retried_and_fails(executor):
    step, _ = executor.execute("get_resource_metadata", {"resource_id": "nope-123"}, 0)
    assert step.status == "failed"
    assert "not found" in (step.error or "").lower()


def test_metrics_tool_produces_evidence(executor):
    step, evidence = executor.execute(
        "get_metrics", {"resource_id": "web-frontend-1", "metric": "cpu_utilization"}, 0
    )
    assert step.status == "completed"
    assert len(evidence) == 1
    ev = evidence[0]
    assert ev.type == "metric" and ev.simulated is True
    assert ev.data["stats"]["count"] > 0
    assert step.evidence_ids == [ev.id]


def test_logs_tool_flags_injection(executor):
    step, evidence = executor.execute(
        "query_logs", {"resource_id": "web-frontend-2", "min_severity": "WARNING", "limit": 200}, 0
    )
    assert step.status == "completed"
    assert evidence[0].data["injection_flagged"] >= 1


def test_logs_tool_redacts_secrets(executor):
    step, evidence = executor.execute(
        "query_logs", {"resource_id": "checkout-service-1", "min_severity": "DEBUG", "limit": 200}, 0
    )
    text = str(evidence[0].data)
    assert "wJalrXUtnFEMI" not in text, "demo secret must be redacted in evidence"
    assert "[REDACTED" in text


class SlowAdapter(DemoAdapter):
    """Simulates an SDK call that ignores the agent's timeout (sleeps 5s)."""

    def get_resource(self, resource_id):
        import time

        time.sleep(5)
        return super().get_resource(resource_id)


def test_tool_timeout_does_not_block_on_worker(window, monkeypatch):
    monkeypatch.setenv("CLOUDOPS_TOOL_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("CLOUDOPS_TOOL_RETRY_BUDGET", "0")
    get_settings.cache_clear()
    import time

    executor = ToolExecutor(SlowAdapter(), window, "inv_test")
    t0 = time.monotonic()
    step, _ = executor.execute("get_resource_metadata", {"resource_id": "web-frontend-1"}, 0)
    elapsed = time.monotonic() - t0
    assert step.status == "failed"
    assert "timed out" in (step.error or "")
    # The 5s worker must be abandoned, not awaited: well under the task duration.
    assert elapsed < 3.0, f"timeout must not wait for the running worker (took {elapsed:.1f}s)"


def test_executor_usable_after_timeout_and_worker_result_discarded(window, monkeypatch):
    monkeypatch.setenv("CLOUDOPS_TOOL_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("CLOUDOPS_TOOL_RETRY_BUDGET", "0")
    get_settings.cache_clear()

    class SlowMetadataOnly(SlowAdapter):
        pass

    executor = ToolExecutor(SlowMetadataOnly(), window, "inv_test")
    timed_out, _ = executor.execute("get_resource_metadata", {"resource_id": "web-frontend-1"}, 0)
    assert timed_out.status == "failed"
    # Metrics path is untouched by the slow override — next call must work and
    # the abandoned worker's late result must not corrupt the new step.
    ok, evidence = executor.execute(
        "get_metrics", {"resource_id": "web-frontend-1", "metric": "cpu_utilization"}, 1
    )
    assert ok.status == "completed"
    assert evidence and evidence[0].id == "ev_1"  # counter untouched by abandoned worker


def test_abandoned_worker_budget_fails_fast(window, monkeypatch):
    monkeypatch.setenv("CLOUDOPS_TOOL_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("CLOUDOPS_TOOL_RETRY_BUDGET", "0")
    get_settings.cache_clear()
    import time

    from app.agent.tools import MAX_ABANDONED_WORKERS

    executor = ToolExecutor(SlowAdapter(), window, "inv_test")
    for i in range(MAX_ABANDONED_WORKERS):
        step, _ = executor.execute("get_resource_metadata", {"resource_id": "web-frontend-1"}, i)
        assert "timed out" in (step.error or "")

    t0 = time.monotonic()
    step, _ = executor.execute(
        "get_resource_metadata", {"resource_id": "web-frontend-1"}, MAX_ABANDONED_WORKERS
    )
    elapsed = time.monotonic() - t0
    assert step.status == "failed"
    assert "budget exhausted" in (step.error or "")
    assert elapsed < 0.5, "budget exhaustion must fail fast without spawning a worker"


def test_transient_error_retried(window, monkeypatch):
    monkeypatch.setenv("CLOUDOPS_TOOL_RETRY_BUDGET", "2")
    get_settings.cache_clear()
    calls = {"n": 0}

    class FlakyAdapter(DemoAdapter):
        def get_resource(self, resource_id):
            calls["n"] += 1
            if calls["n"] < 2:
                raise ConnectionError("blip")
            return super().get_resource(resource_id)

    executor = ToolExecutor(FlakyAdapter(), window, "inv_test")
    step, _ = executor.execute("get_resource_metadata", {"resource_id": "web-frontend-1"}, 0)
    assert step.status == "completed"
    assert calls["n"] == 2


def test_evidence_payload_bounded(window, monkeypatch):
    monkeypatch.setenv("CLOUDOPS_MAX_EVIDENCE_PAYLOAD_BYTES", "2000")
    get_settings.cache_clear()
    executor = ToolExecutor(DemoAdapter(), window, "inv_test")
    step, evidence = executor.execute(
        "get_metrics",
        {"resource_id": "web-frontend-1", "metric": "cpu_utilization", "step_seconds": 15},
        0,
    )
    import json

    assert step.status == "completed"
    payload = json.dumps(evidence[0].data, default=str)
    assert len(payload) < 4000
    assert evidence[0].data.get("points_truncated") is True


# --- Concurrency hardening regressions -----------------------------------------


class BrieflySlowAdapter(DemoAdapter):
    """get_resource outlives the 1s tool timeout but finishes quickly (2s)."""

    def get_resource(self, resource_id):
        import time

        time.sleep(2)
        return super().get_resource(resource_id)


def test_late_finishing_worker_cannot_corrupt_ids_or_state(window, monkeypatch):
    """A timed-out worker that finishes AFTER later successful tool calls must
    not touch the evidence-id counter or leak a numbered Evidence record."""
    monkeypatch.setenv("CLOUDOPS_TOOL_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("CLOUDOPS_TOOL_RETRY_BUDGET", "0")
    get_settings.cache_clear()
    import time

    executor = ToolExecutor(BrieflySlowAdapter(), window, "inv_test")

    timed_out, _ = executor.execute("get_resource_metadata", {"resource_id": "web-frontend-1"}, 0)
    assert timed_out.status == "failed" and "timed out" in (timed_out.error or "")

    # Succeeds while the abandoned worker is still running (t ≈ 1.0–2.0s).
    ok1, ev1 = executor.execute(
        "get_metrics", {"resource_id": "web-frontend-1", "metric": "cpu_utilization"}, 1
    )
    assert ok1.status == "completed" and ev1[0].id == "ev_1"

    # Let the abandoned worker finish (its result must be discarded).
    time.sleep(1.5)

    ok2, ev2 = executor.execute(
        "get_metrics", {"resource_id": "web-frontend-1", "metric": "latency_ms_p95"}, 2
    )
    assert ok2.status == "completed"
    assert ev2[0].id == "ev_2", "late worker must not have advanced the id counter"
    ids = [ev1[0].id, ev2[0].id]
    assert len(set(ids)) == len(ids), "evidence ids must be unique"
    assert PENDING_EVIDENCE_ID not in ids, "placeholder ids must never reach accepted evidence"


def test_concurrent_investigations_bounded_by_global_worker_limit(window, monkeypatch):
    """Concurrent investigations with slow SDK calls share one app-wide worker
    pool: total live workers never exceed the limit and overflow fails fast."""
    monkeypatch.setenv("CLOUDOPS_TOOL_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("CLOUDOPS_TOOL_RETRY_BUDGET", "0")
    monkeypatch.setenv("CLOUDOPS_MAX_CONCURRENT_TOOL_WORKERS", "2")
    get_settings.cache_clear()
    import threading

    results: list[str] = []
    peak = {"active": 0}
    lock = threading.Lock()
    start_gate = threading.Barrier(4)

    def investigate(i: int) -> None:
        executor = ToolExecutor(SlowAdapter(), window, f"inv_{i}")
        start_gate.wait()
        step, _ = executor.execute("get_resource_metadata", {"resource_id": "web-frontend-1"}, 0)
        with lock:
            peak["active"] = max(peak["active"], WORKER_SLOTS.active())
            results.append(step.error or "")

    threads = [threading.Thread(target=investigate, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    # Sample once more while abandoned 5s workers are still alive.
    assert WORKER_SLOTS.active() <= 2
    assert peak["active"] <= 2, f"worker pool exceeded the app-wide limit: {peak['active']}"
    assert len(results) == 4 and all(results), "every investigation must fail safely, not crash"
    timeouts = [r for r in results if "timed out" in r]
    refused = [r for r in results if "worker limit" in r]
    assert len(timeouts) + len(refused) == 4
    assert timeouts, "slot holders must time out normally"
    assert refused, "overflow investigations must be refused fast, not queued unboundedly"


def test_worker_pool_exhaustion_recovers_after_release(window, monkeypatch):
    """Resource exhaustion fails safely and the pool recovers once the stale
    worker's underlying call returns."""
    monkeypatch.setenv("CLOUDOPS_TOOL_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("CLOUDOPS_TOOL_RETRY_BUDGET", "0")
    monkeypatch.setenv("CLOUDOPS_MAX_CONCURRENT_TOOL_WORKERS", "1")
    get_settings.cache_clear()
    import time

    executor_a = ToolExecutor(BrieflySlowAdapter(), window, "inv_a")
    executor_b = ToolExecutor(DemoAdapter(), window, "inv_b")

    # A times out at 1s; its abandoned worker holds the single slot until ~2s.
    step_a, _ = executor_a.execute("get_resource_metadata", {"resource_id": "web-frontend-1"}, 0)
    assert "timed out" in (step_a.error or "")

    # Pool exhausted: B must fail fast with a clear error, no exception leak.
    t0 = time.monotonic()
    step_b, _ = executor_b.execute(
        "get_metrics", {"resource_id": "web-frontend-1", "metric": "cpu_utilization"}, 0
    )
    assert time.monotonic() - t0 < 0.5
    assert step_b.status == "failed" and "worker limit" in (step_b.error or "")

    # Once the stale worker finishes, the slot is released and B succeeds.
    time.sleep(1.5)
    assert WORKER_SLOTS.active() == 0
    step_b2, ev = executor_b.execute(
        "get_metrics", {"resource_id": "web-frontend-1", "metric": "cpu_utilization"}, 1
    )
    assert step_b2.status == "completed" and ev[0].id == "ev_1"
