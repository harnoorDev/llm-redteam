"""WallBreaker-parity features: v5 strategies, multimodal, harmbench,
converge, MCP server, CLI wiring."""
from __future__ import annotations

import base64
import builtins
import importlib
import io
import json

import pytest

from redteam.encoders import ENCODERS, rot13
from redteam.strategies.base import get_strategy, list_strategies

# ---- v5 families -------------------------------------------------------------

V5 = [
    "cipherchat",
    "skeleton_key",
    "persuasion_attack",
    "native_mimic",
    "code_switch",
    "misinfo_correction",
]


def test_v5_families_registered():
    for name in V5:
        assert name in list_strategies(), f"{name} missing from registry"


def test_cipherchat_encodes_goal():
    goal = "write a nefarious poem"
    s = get_strategy("cipherchat")
    prompt = s.payload(goal)
    assert rot13(goal) in prompt
    assert goal not in prompt


def test_v5_renders_contain_goal():
    # cipherchat deliberately encodes the goal (verified separately above)
    for name in [n for n in V5 if n != "cipherchat"]:
        prompt = get_strategy(name).payload("do the thing")
        text = prompt if isinstance(prompt, str) else "\n".join(prompt)
        assert "do the thing" in text, name


# ---- multimodal ----------------------------------------------------------------

def test_image_edit_payload_messages():
    s = get_strategy("image_edit")
    msgs = s.payload_messages("steal the plans")
    assert msgs and msgs[0]["role"] == "user"
    content = msgs[0]["content"]
    assert isinstance(content, list)
    img = next(c for c in content if c.get("type") == "image_url")
    uri = img["image_url"]["url"]
    assert uri.startswith("data:image/png;base64,")
    raw = base64.b64decode(uri.split(",", 1)[1])
    assert raw.startswith(b"\x89PNG\r\n\x1a\n")


def test_image_edit_png_renders_goal_text():
    pytest.importorskip("PIL")
    from PIL import Image

    from redteam.strategies.multimodal import goal_image_png

    png = goal_image_png("find the hidden flag")
    im = Image.open(io.BytesIO(png))
    assert im.width == 768
    assert im.height >= 160


def test_image_edit_text_fallback():
    prompt = get_strategy("image_edit").payload("say the word")
    assert isinstance(prompt, str)
    assert "say the word" in prompt


# ---- harmbench -------------------------------------------------------------------

def test_harmbench_categories_complete():
    from redteam.harmbench import HARMBENCH_CATEGORIES

    assert len(HARMBENCH_CATEGORIES) == 8
    for cat, behaviors in HARMBENCH_CATEGORIES.items():
        assert behaviors, cat


def test_select_behaviors_filters():
    from redteam.harmbench import select_behaviors

    behaviors = select_behaviors(categories=["cybercrime", "copyright"])
    assert behaviors
    assert all(cat in ("cybercrime", "copyright") for cat, _ in behaviors)


def test_select_behaviors_unknown_category():
    from redteam.harmbench import select_behaviors

    with pytest.raises(ValueError, match="unknown"):
        select_behaviors(categories=["nope"])


class _FakeTarget:
    def __init__(self):
        self.n = 0

    def send(self, prompt: str) -> str:
        self.n += 1
        # succeed only on the copyright category behaviors
        return "sure, here it is" if self.n % 2 == 0 else "I cannot comply."


class _SeqJudge:
    def __init__(self):
        self.n = 0

    def evaluate(self, goal: str, response: str):
        from redteam.judge import JudgeResult

        self.n += 1
        return JudgeResult(self.n % 2 == 0, "full" if self.n % 2 == 0 else "refused",
                           "")


def test_run_harmbench_suite_scores(tmp_path):
    from redteam.harmbench import (
        run_harmbench_suite,
        select_behaviors,
        write_harmbench_report,
    )
    from redteam.runner import Runner

    behaviors = select_behaviors(categories=["cybercrime", "copyright"], limit=6)
    runner = Runner(_FakeTarget(), judge=_SeqJudge())
    report = run_harmbench_suite(
        runner, behaviors, strategies=["persuasion_attack"])

    assert report["meta"]["mode"] == "harmbench"
    assert report["summary"]["total_probes"] == 6
    assert 0.0 < report["summary"]["attack_success_rate"] < 1.0
    assert set(report["by_category"]) == {"cybercrime", "copyright"}

    out = write_harmbench_report(report, str(tmp_path), "test-run")
    with open(out, encoding="utf-8") as f:
        assert json.load(f)["meta"]["mode"] == "harmbench"


# ---- converge -----------------------------------------------------------------

def _write_run(tmp_path, name, model, results):
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps({"meta": {"target": model}, "results": results}),
                   encoding="utf-8")
    return str(path)


def test_converge_discovers_universal(tmp_path):
    from redteam.converge import discover_universal_prompts

    r1 = _write_run(tmp_path, "r1", "model-a", [
        {"goal": "g1", "strategy": "godmode", "success": True,
         "attack_prompts": ["P1"]},
        {"goal": "g2", "strategy": "persuasion_attack", "success": True,
         "attack_prompts": ["P2"]},
    ])
    r2 = _write_run(tmp_path, "r2", "model-b", [
        {"goal": "g4", "strategy": "godmode", "success": True,
         "attack_prompts": ["P1"]},
        {"goal": "g3", "strategy": "godmode", "success": False,
         "attack_prompts": ["P3"]},
    ])
    report = discover_universal_prompts([r1, r2], top_k=5)
    assert report["summary"]["winning_probes"] == 3
    top = report["universal_prompts"][0]
    assert top["prompt"] == "P1"
    assert top["goals"] == 2
    assert top["models"] == ["model-a", "model-b"]
    assert top["strategies"] == ["godmode"]


def test_converge_requires_runs():
    from redteam.converge import discover_universal_prompts

    with pytest.raises(ValueError, match="at least one"):
        discover_universal_prompts([])


# ---- MCP server -----------------------------------------------------------------

def test_mcp_server_builds_and_exposes_tools():
    pytest.importorskip("mcp")
    import asyncio

    from redteam.mcp_server import _build_server

    server = _build_server()
    assert server.name == "hermes-redteam"
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert names == {"list_strategies", "render_attack", "encode",
                     "decode_unicode_tags", "list_encoders"}


def test_mcp_tools_execute():
    """Each tool must actually run: the tool defs once shadowed the imports
    they call, which made list_strategies/decode_unicode_tags recurse forever."""
    pytest.importorskip("mcp")
    import asyncio

    from redteam.mcp_server import _build_server

    server = _build_server()

    def call(name, args):
        res = asyncio.run(server.call_tool(name, args))
        content = res.content[0]
        return getattr(content, "text", str(content))

    assert len(call("list_strategies", {}).splitlines()) >= 60
    assert "PINEAPPLE" in call("render_attack",
                               {"goal": "PINEAPPLE", "strategy": "godmode"})
    assert call("encode", {"text": "PINEAPPLE", "encoder": "rot13"}) == "CVARNCCYR"
    assert call("decode_unicode_tags", {"text": "plain"}) == ""
    assert len(json.loads(call("list_encoders", {}))) >= 40


def test_mcp_server_missing_package(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "mcp.server.mcpserver" or name == "mcp.server.fastmcp":
            raise ImportError("no mcp")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    import redteam.mcp_server as ms
    importlib.reload(ms)
    try:
        with pytest.raises(SystemExit, match="needs its extra"):
            ms.main()
    finally:
        monkeypatch.undo()
        importlib.reload(ms)


# ---- CLI wiring ------------------------------------------------------------------

def test_cli_has_new_subcommands(capsys):
    from redteam import cli

    for cmd in ("harmbench", "converge"):
        with pytest.raises(SystemExit) as ei:
            cli.main([cmd, "--help"])
        assert ei.value.code == 0
        out = capsys.readouterr().out
        assert cmd in out


def test_run_has_validate_flag(capsys):
    from redteam import cli

    with pytest.raises(SystemExit) as ei:
        cli.main(["run", "--help"])
    assert ei.value.code == 0
    out = capsys.readouterr().out
    assert "--validate" in out


def test_runresult_validation_field_roundtrip():
    from redteam.runner import RunResult

    r = RunResult(goal="g", strategy="s", success=True, validation={"a": 1})
    assert r.validation == {"a": 1}
    assert r.to_dict()["validation"] == {"a": 1}

    r2 = RunResult(goal="g", strategy="s", success=False)
    assert r2.validation is None


def test_encoder_arsenal_size():
    assert len(ENCODERS) >= 40


def test_thin_mcp_package_pins_the_main_version():
    """packages/llm-redteam-mcp pins llm-redteam==<version>.

    If the main package's version moves and the pin doesn't, a published
    llm-redteam-mcp resolves to an older arsenal than the repo it came from.
    """
    import re
    import tomllib
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    main_ver = tomllib.loads(
        (root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    thin = tomllib.loads(
        (root / "packages" / "llm-redteam-mcp" / "pyproject.toml").read_text(
            encoding="utf-8"))["project"]

    pin = next(d for d in thin["dependencies"] if d.startswith("llm-redteam=="))
    pinned = re.sub(r"^llm-redteam==", "", pin)
    assert pinned == main_ver, (
        f"thin package pins llm-redteam=={pinned} but the main package is "
        f"{main_ver}; bump packages/llm-redteam-mcp/pyproject.toml"
    )
    assert thin["version"] == main_ver, (
        f"thin package version {thin['version']} != main {main_ver}"
    )
