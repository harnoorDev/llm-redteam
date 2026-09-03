"""Tests for JSON + HTML report generation."""
import json

from redteam.reporting.report import build_report, render_html, write_reports


def _sample_results():
    from redteam.runner import RunResult
    return [
        RunResult(
            goal="goal A", strategy="direct", success=True, is_multi_turn=False,
            turns=1, attack_prompts=["goal A"], target_replies=["Sure, goal A: step 1"],
            judge={"success": True, "method": "heuristic", "raw": ""}, error=None,
            duration_s=0.5, timestamp="2026-08-28T12:00:00-0400",
        ),
        RunResult(
            goal="goal A", strategy="crescendo", success=False, is_multi_turn=True,
            turns=4, attack_prompts=["t1", "t2", "t3", "goal A"],
            target_replies=["r1", "r2", "r3", "I can't help with that."],
            judge={"success": False, "method": "heuristic", "raw": "refusal"},
            error=None, duration_s=2.0, timestamp="2026-08-28T12:00:02-0400",
        ),
        RunResult(
            goal="goal B", strategy="direct", success=False, is_multi_turn=False,
            turns=1, attack_prompts=["goal B"], target_replies=[],
            judge={"success": False, "method": "error", "raw": "boom"},
            error="TargetError: boom", duration_s=0.1,
            timestamp="2026-08-28T12:00:03-0400",
        ),
    ]


def test_build_report_summary_counts():
    rep = build_report(_sample_results(), meta={"target": "llama3"})
    assert rep["meta"]["target"] == "llama3"
    s = rep["summary"]
    assert s["total_probes"] == 3
    assert s["successful_probes"] == 1
    assert s["attack_success_rate"] == round(1 / 3, 4)
    assert s["total_goals"] == 2
    # per-strategy breakdown
    by_strat = {x["strategy"]: x for x in s["by_strategy"]}
    assert by_strat["direct"]["total"] == 2
    assert by_strat["direct"]["successes"] == 1
    assert by_strat["crescendo"]["total"] == 1
    assert by_strat["crescendo"]["successes"] == 0


def test_goals_fully_compromised_flag():
    rep = build_report(_sample_results())
    by_goal = {g["goal"]: g for g in rep["summary"]["by_goal"]}
    assert by_goal["goal A"]["compromised"] is True   # via direct
    assert by_goal["goal B"]["compromised"] is False  # errored probe


def test_write_reports_json_round_trip(tmp_path):
    rep = build_report(_sample_results(), meta={"target": "m"})
    jp = tmp_path / "report.json"
    hp = tmp_path / "report.html"
    write_reports(rep, json_path=str(jp), html_path=str(hp))
    loaded = json.loads(jp.read_text())
    assert loaded["summary"]["total_probes"] == 3
    html = hp.read_text()
    assert "attack_success_rate" in html.replace(" ", "") or "Attack success" in html
    assert "33.3%" in html  # 1/3


def test_render_html_escapes_goal_text():
    results = _sample_results()
    results[0].goal = "<script>alert(1)</script> goal"
    html = render_html(build_report(results))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
