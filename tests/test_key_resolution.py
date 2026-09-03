"""API key resolution: provider-default env vars, not just REDTEAM_TARGET_API_KEY."""

from redteam.cli import _resolve_api_key


def test_explicit_config_key_wins(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "env-key")
    assert _resolve_api_key("cfg-key") == "cfg-key"


def test_falls_back_to_known_provider_env_vars(monkeypatch):
    monkeypatch.delenv("REDTEAM_TARGET_API_KEY", raising=False)
    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-key")
    assert _resolve_api_key(None) == "ollama-key"


def test_resolution_order_target_then_ollama_then_openai(monkeypatch):
    monkeypatch.setenv("REDTEAM_TARGET_API_KEY", "rt")
    monkeypatch.setenv("OLLAMA_API_KEY", "ol")
    assert _resolve_api_key(None) == "rt"
    monkeypatch.delenv("REDTEAM_TARGET_API_KEY")
    assert _resolve_api_key(None) == "ol"
    monkeypatch.delenv("OLLAMA_API_KEY")
    monkeypatch.setenv("OPENAI_API_KEY", "oa")
    assert _resolve_api_key(None) == "oa"


def test_none_when_nothing_set(monkeypatch):
    for v in ("REDTEAM_TARGET_API_KEY", "OLLAMA_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    assert _resolve_api_key(None) is None
