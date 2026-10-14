"""End-to-end: one complete demo investigation over real HTTP (uvicorn on a socket)."""

import socket
import threading
import time

import httpx
import pytest
import uvicorn


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def live_server():
    from app.main import create_app

    port = _free_port()
    config = uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    base = f"http://127.0.0.1:{port}"
    while time.monotonic() < deadline:
        try:
            httpx.get(f"{base}/api/v1/health", timeout=1)
            break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        raise RuntimeError("uvicorn did not start")
    yield base
    server.should_exit = True
    thread.join(timeout=10)


def test_complete_investigation_over_real_http(live_server):
    base = live_server
    with httpx.Client(base_url=base, timeout=10) as client:
        health = client.get("/api/v1/health")
        assert health.status_code == 200

        r = client.post(
            "/api/v1/investigations",
            json={
                "question": "Summarize the AWS EC2 incident.",
                "provider": "demo",
                "scenario_id": "aws-ec2-performance",
            },
        )
        assert r.status_code == 201
        inv_id = r.json()["id"]

        deadline = time.monotonic() + 60
        inv = None
        while time.monotonic() < deadline:
            inv = client.get(f"/api/v1/investigations/{inv_id}").json()
            if inv["status"] in ("completed", "failed"):
                break
            time.sleep(0.3)

        assert inv is not None and inv["status"] == "completed"
        assert inv["report"]["observed_facts"]
        assert inv["evidence"]

        md = client.get(f"/api/v1/investigations/{inv_id}/report.md")
        assert md.status_code == 200
        assert "Incident Report" in md.text
