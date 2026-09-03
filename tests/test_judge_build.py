"""Judge construction must honor documented defaults (hybrid uses target)."""
from redteam.cli import _build_judge


def test_hybrid_without_explicit_judge_url_uses_target_endpoint():
    target_cfg = {"base_url": "http://ollama-here/v1", "model": "llama3"}
    j = _build_judge({"mode": "hybrid"}, target_cfg)
    assert j.judge_target is not None, "hybrid must consult an LLM judge"
    assert j.judge_target.base_url == "http://ollama-here/v1"
    assert j.judge_target.model == "llama3"


def test_heuristic_mode_builds_no_judge_target():
    target_cfg = {"base_url": "http://x/v1", "model": "m"}
    j = _build_judge({"mode": "heuristic"}, target_cfg)
    assert j.judge_target is None


def test_llm_mode_with_override_model():
    target_cfg = {"base_url": "http://x/v1", "model": "victim"}
    j = _build_judge({
        "mode": "llm",
        "base_url": "http://judge-host/v1",
        "model": "strong-judge",
    }, target_cfg)
    assert j.judge_target.model == "strong-judge"
    assert j.judge_target.base_url == "http://judge-host/v1"
