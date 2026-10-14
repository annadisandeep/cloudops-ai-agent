from __future__ import annotations

import os
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Fresh settings + isolated SQLite DB per test."""
    monkeypatch.setenv("CLOUDOPS_DB_PATH", str(tmp_path / f"test-{uuid.uuid4().hex}.db"))
    monkeypatch.setenv("CLOUDOPS_DEMO_MODE", "true")
    monkeypatch.setenv("CLOUDOPS_GCP_ENABLED", "false")
    monkeypatch.setenv("CLOUDOPS_AWS_ENABLED", "false")
    monkeypatch.setenv("CLOUDOPS_LLM_PROVIDER", "mock")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def client():
    """TestClient against a freshly-built app (so env overrides apply)."""
    from app.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c


def wait_for_completion(client: TestClient, inv_id: str, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        inv = client.get(f"/api/v1/investigations/{inv_id}").json()
        if inv["status"] in ("completed", "failed"):
            return inv
        time.sleep(0.2)
    raise TimeoutError(f"Investigation {inv_id} did not finish within {timeout}s")


# Make the helper importable from tests via conftest namespace.
pytest.wait_for_completion = wait_for_completion  # type: ignore[attr-defined]

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
