"""Configuration behavior: LLM model default, env override, label mapping."""

from app.config import get_settings

CURRENT_STABLE_GEMINI = "gemini-3.8-flash"


def test_default_gemini_model_is_current_stable(monkeypatch):
    monkeypatch.delenv("CLOUDOPS_GEMINI_MODEL", raising=False)
    get_settings.cache_clear()
    assert get_settings().gemini_model == CURRENT_STABLE_GEMINI


def test_gemini_model_env_override(monkeypatch):
    monkeypatch.setenv("CLOUDOPS_GEMINI_MODEL", "gemini-4-argon")
    get_settings.cache_clear()
    assert get_settings().gemini_model == "gemini-4-argon"


def test_llm_model_label_for_mock_provider(monkeypatch):
    monkeypatch.setenv("CLOUDOPS_LLM_PROVIDER", "mock")
    get_settings.cache_clear()
    assert get_settings().llm_model_label == "deterministic-v1"


def test_llm_model_label_for_gemini_provider(monkeypatch):
    monkeypatch.setenv("CLOUDOPS_LLM_PROVIDER", "gemini")
    monkeypatch.delenv("CLOUDOPS_GEMINI_MODEL", raising=False)
    get_settings.cache_clear()
    assert get_settings().llm_model_label == CURRENT_STABLE_GEMINI


def test_config_endpoint_reflects_model_override(client, monkeypatch):
    monkeypatch.setenv("CLOUDOPS_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("CLOUDOPS_GEMINI_MODEL", "gemini-custom-override")
    get_settings.cache_clear()
    body = client.get("/api/v1/config").json()
    assert body["llm"] == {"provider": "gemini", "model": "gemini-custom-override"}
    # The API key must never appear anywhere in the response.
    assert "key" not in str(body["llm"]).lower()


def test_gemini_api_key_never_leaks_from_any_endpoint(client, monkeypatch, caplog):
    """With a configured key, no public endpoint response and no log line may
    contain the key value (docker-compose passes it as a backend env var)."""
    sentinel = "SENTINEL-gemini-key-1a2b3c4d5e6f"
    monkeypatch.setenv("CLOUDOPS_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("CLOUDOPS_GEMINI_API_KEY", sentinel)
    get_settings.cache_clear()

    import logging

    with caplog.at_level(logging.DEBUG):
        responses = [
            client.get("/api/v1/config"),
            client.get("/api/v1/providers"),
            client.get("/api/v1/health"),
            client.get("/api/v1/overview"),
            client.get("/api/v1/scenarios"),
            client.get("/openapi.json"),
        ]
    for r in responses:
        assert sentinel not in r.text, f"API key leaked via {r.request.url}"
    assert sentinel not in caplog.text, "API key leaked into application logs"


def test_gemini_planner_uses_configured_model(monkeypatch):
    monkeypatch.setenv("CLOUDOPS_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("CLOUDOPS_GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("CLOUDOPS_GEMINI_MODEL", "gemini-override-check")
    get_settings.cache_clear()
    from unittest.mock import MagicMock, patch

    from app.agent.planner import GeminiPlanner

    with patch("google.genai.Client", return_value=MagicMock()):
        planner = GeminiPlanner()
    assert planner._model == "gemini-override-check"
