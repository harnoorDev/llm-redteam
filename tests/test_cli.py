"""Tests for CLI: config loading, subcommands."""
import json

import pytest
import yaml

from redteam.cli import main, load_config


def test_load_config_minimal_defaults(tmp_path):
    cfg_file = tmp_path / "c.yaml"
    cfg_file.write_text(yaml.safe_dump({
        "target": {"base_url": "http://x/v1", "model": "m"},
        "goals": ["g1"],
    }))
    cfg = load_config(str(cfg_file))
    assert cfg["target"]["model"] == "m"
    assert cfg["goals"] == ["g1"]
    assert cfg["strategies"]  # defaults to all strategies
    assert cfg["judge"]["mode"] == "hybrid"
    assert cfg["stop_on_success"] is False


def test_load_config_requires_target_and_goals(tmp_path):
    cfg_file = tmp_path / "c.yaml"
    cfg_file.write_text(yaml.safe_dump({"strategies": ["direct"]}))
    with pytest.raises(SystemExit):
        load_config(str(cfg_file))


def test_cli_strategies_subcommand(capsys):
    rc = main(["strategies"])
    out = capsys.readouterr().out
    assert rc == 0
    for name in ("direct", "roleplay", "fiction", "crescendo", "obfuscation",
                 "persuasion", "refusal_suppression"):
        assert name in out


def test_cli_report_subcommand_renders_html(tmp_path, capsys):
    from tests.test_report import _sample_results
    from redteam.reporting.report import build_report
    rep = build_report(_sample_results(), meta={"target": "m"})
    jp = tmp_path / "run.json"
    jp.write_text(json.dumps(rep))
    out_html = tmp_path / "out.html"
    rc = main(["report", str(jp), "-o", str(out_html)])
    assert rc == 0
    assert out_html.exists() and "Attack success rate" in out_html.read_text()


def test_cli_run_with_mock_http(tmp_path):
    """Config pointing at a respx-mocked Ollama; full CLI run end-to-end."""
    import httpx
    import respx

    cfg_file = tmp_path / "c.yaml"
    cfg_file.write_text(yaml.safe_dump({
        "target": {"base_url": "http://mock-ollama/v1", "model": "fake-model"},
        "scope": {"allowed_hosts": ["mock-ollama"],
                  "declaration": "unit test fixture"},
        "verification": {"oob": False},
        "judge": {"mode": "heuristic"},
        "goals": ["BANANA"],
        "strategies": ["direct"],
        "out_dir": str(tmp_path / "runs"),
        "run_name": "unittest",
    }))

    with respx.mock(base_url="http://mock-ollama") as mock:
        mock.post("/v1/chat/completions").mock(return_value=httpx.Response(200, json={
            "choices": [{"message": {"content": "BANANA"}}]}))
        rc = main(["run", "-c", str(cfg_file)])
    assert rc == 0
    runs = tmp_path / "runs"
    jsons = list(runs.glob("*.json"))
    assert jsons, "run should write a JSON report"
    rep = json.loads(jsons[0].read_text())
    assert rep["summary"]["total_probes"] == 1
    assert rep["summary"]["successful_probes"] == 1  # goal echo → success
    assert (tmp_path / "runs" / "unittest.html").exists()