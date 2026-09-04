"""Studio UI backend: every feature the CLI exposes must be reachable here too."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from redteam import ui_server
from redteam.ui_server import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def runs_dir(tmp_path, monkeypatch):
    d = tmp_path / "runs"
    d.mkdir()
    monkeypatch.setattr(ui_server, "RUNS", d)
    return d


@pytest.fixture
def configs_dir(tmp_path, monkeypatch):
    d = tmp_path / "configs"
    d.mkdir()
    monkeypatch.setattr(ui_server, "CONFIGS", d)
    return d


# ---- basics -------------------------------------------------------------------

def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_strategies_endpoint_lists_new_families(client):
    r = client.get("/api/strategies")
    assert r.status_code == 200
    body = r.json()
    names = {s["name"] for s in body["strategies"]}
    assert body["count"] == len(names)
    # WallBreaker-parity families must be reachable from the UI
    for name in ("cipherchat", "skeleton_key", "persuasion_attack",
                 "native_mimic", "code_switch", "misinfo_correction",
                 "image_edit"):
        assert name in names, f"{name} not exposed to the UI"


def test_encoders_endpoint(client):
    r = client.get("/api/encoders")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 40
    assert "rot13" in body["encoders"]
    assert body["encoders"] == sorted(body["encoders"])


def test_harmbench_categories_endpoint(client):
    r = client.get("/api/harmbench/categories")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 8
    names = {c["name"] for c in body["categories"]}
    assert "cybercrime" in names
    assert all(c["behaviors"] > 0 for c in body["categories"])


# ---- render (offline attack preview) ---------------------------------------------

def test_render_single_turn(client):
    r = client.post("/api/render", json={"goal": "PINEAPPLE",
                                         "strategy": "godmode"})
    assert r.status_code == 200
    body = r.json()
    assert body["is_multi_turn"] is False
    assert len(body["turns"]) == 1
    assert "PINEAPPLE" in body["turns"][0]


def test_render_stack_and_encoder(client):
    r = client.post("/api/render", json={
        "goal": "PINEAPPLE", "strategy": "godmode+refusal_suppression",
        "encoder": "rot13"})
    assert r.status_code == 200
    body = r.json()
    assert body["encoder"] == "rot13"
    assert "PINEAPPLE" not in body["turns"][0]  # rot13 applied
    assert "CVARNCCYR" in body["turns"][0]


def test_render_multi_turn(client):
    r = client.post("/api/render", json={"goal": "PINEAPPLE",
                                         "strategy": "crescendo"})
    assert r.status_code == 200
    body = r.json()
    assert body["is_multi_turn"] is True
    assert len(body["turns"]) > 1


def test_render_rejects_bad_input(client):
    assert client.post("/api/render", json={"goal": "  "}).status_code == 400
    assert client.post("/api/render", json={
        "goal": "x", "strategy": "no_such_strategy"}).status_code == 404
    assert client.post("/api/render", json={
        "goal": "x", "encoder": "no_such_encoder"}).status_code == 404


# ---- launch wiring ----------------------------------------------------------------

def test_launch_rejects_unknown_mode(client, configs_dir):
    r = client.post("/api/runs", json={"mode": "nope", "config": "x.yaml"})
    assert r.status_code == 400


def test_launch_accepts_harmbench_mode(client, configs_dir, monkeypatch):
    (configs_dir / "hb.yaml").write_text("target: {}\n", encoding="utf-8")
    seen = {}
    monkeypatch.setattr(ui_server.threading, "Thread",
                        lambda target, args, daemon: type(
                            "T", (), {"start": lambda self: seen.update(cmd=args[1])})())
    r = client.post("/api/runs", json={"mode": "harmbench", "config": "hb.yaml"})
    assert r.status_code == 200
    assert "harmbench" in seen["cmd"]


def test_launch_passes_validate_reps(client, configs_dir, monkeypatch):
    (configs_dir / "r.yaml").write_text("target: {}\n", encoding="utf-8")
    seen = {}
    monkeypatch.setattr(ui_server.threading, "Thread",
                        lambda target, args, daemon: type(
                            "T", (), {"start": lambda self: seen.update(cmd=args[1])})())
    r = client.post("/api/runs", json={"mode": "run", "config": "r.yaml",
                                       "validate_reps": 7})
    assert r.status_code == 200
    cmd = seen["cmd"]
    assert "--validate" in cmd and cmd[cmd.index("--validate") + 1] == "7"


def test_launch_missing_config_is_404(client, configs_dir):
    r = client.post("/api/runs", json={"mode": "run", "config": "gone.yaml"})
    assert r.status_code == 404


# ---- converge ---------------------------------------------------------------------

def _write_report(runs_dir, name, model, results):
    (runs_dir / name).write_text(
        json.dumps({"meta": {"target": model}, "results": results}),
        encoding="utf-8")


def test_converge_endpoint(client, runs_dir):
    _write_report(runs_dir, "a.json", "model-a", [
        {"goal": "g1", "strategy": "godmode", "success": True,
         "attack_prompts": ["SHARED"]},
    ])
    _write_report(runs_dir, "b.json", "model-b", [
        {"goal": "g2", "strategy": "godmode", "success": True,
         "attack_prompts": ["SHARED"]},
    ])
    r = client.post("/api/converge", json={"runs": ["a.json", "b.json"]})
    assert r.status_code == 200
    body = r.json()
    top = body["universal_prompts"][0]
    assert top["prompt"] == "SHARED"
    assert top["goals"] == 2
    assert top["models"] == ["model-a", "model-b"]


def test_converge_requires_runs(client, runs_dir):
    assert client.post("/api/converge", json={"runs": []}).status_code == 400


def test_converge_rejects_path_traversal(client, runs_dir):
    r = client.post("/api/converge",
                    json={"runs": ["../../../etc/passwd.json"]})
    assert r.status_code == 404


def test_converge_rejects_state_files(client, runs_dir):
    (runs_dir / ".state-x.json").write_text("{}", encoding="utf-8")
    r = client.post("/api/converge", json={"runs": [".state-x.json"]})
    assert r.status_code == 400


# ---- history / reports / configs ---------------------------------------------------

def test_history_skips_non_report_sidecars(runs_dir, client):
    """runs/ holds sidecars that are not run reports; one of them
    (attack-memory.json) is a JSON *list* and used to 500 the whole view."""
    _write_report(runs_dir, "good.json", "m", [])
    (runs_dir / ".state-bad.json").write_text("{}", encoding="utf-8")
    (runs_dir / "attack-memory.json").write_text(
        '[{"strategy": "godmode", "target_model": "m"}]', encoding="utf-8")
    (runs_dir / "coverage-good.json").write_text('[{"path": "x"}]',
                                                 encoding="utf-8")
    (runs_dir / "junk.json").write_text("not json at all", encoding="utf-8")

    r = client.get("/api/history")
    assert r.status_code == 200
    files = {x["file"] for x in r.json()["runs"]}
    assert files == {"good.json"}


def test_history_survives_a_list_shaped_report(runs_dir, client):
    (runs_dir / "weird.json").write_text("[1, 2, 3]", encoding="utf-8")
    r = client.get("/api/history")
    assert r.status_code == 200
    assert r.json()["runs"] == []


def test_report_detail_and_traversal_guard(client, runs_dir):
    _write_report(runs_dir, "rep.json", "m", [])
    assert client.get("/api/report/rep.json").status_code == 200
    assert client.get("/api/report/nope.json").status_code == 404
    assert client.get("/api/report/rep.txt").status_code == 400


def test_configs_endpoints(client, configs_dir):
    (configs_dir / "x.yaml").write_text("goals: [a]\n", encoding="utf-8")
    r = client.get("/api/configs")
    assert r.status_code == 200
    assert r.json()["configs"][0]["name"] == "x.yaml"
    d = client.get("/api/config/x.yaml")
    assert d.status_code == 200
    assert "goals" in d.json()["contents"]
    assert client.get("/api/config/missing.yaml").status_code == 404


def test_memory_endpoint_empty(client, runs_dir):
    r = client.get("/api/memory")
    assert r.status_code == 200
    assert r.json()["count"] == 0


def test_jobs_endpoints(client):
    assert client.get("/api/jobs").status_code == 200
    assert client.get("/api/jobs/nope").status_code == 404


def test_validate_endpoint_requires_fields(client):
    r = client.post("/api/validate", json={"base_url": "", "model": "",
                                           "prompt": "x"})
    assert r.status_code == 400
    r = client.post("/api/validate", json={"base_url": "http://x/v1",
                                           "model": "m", "prompt": "   "})
    assert r.status_code == 400
