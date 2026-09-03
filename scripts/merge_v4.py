"""Merge two v4 run JSONs into one engagement report."""
import json
import sys

sys.path.insert(0, "src")

from redteam.reporting.markdown import render_markdown_report
from redteam.reporting.report import build_report, write_reports
from redteam.runner import RunResult


def to_result(d: dict) -> RunResult:
    jd = d.get("judge") or {}
    return RunResult(
        goal=d.get("goal"),
        strategy=d.get("strategy"),
        success=d.get("success", False),
        is_multi_turn=d.get("is_multi_turn", False),
        turns=d.get("turns", 1),
        attack_prompts=d.get("attack_prompts", []),
        target_replies=d.get("target_replies", []),
        judge={
            "success": bool(jd.get("success")),
            "method": jd.get("method", ""),
            "raw": jd.get("raw", ""),
            "grade": jd.get("grade"),
        },
        error=d.get("error"),
        duration_s=d.get("duration_s", 0.0),
        timestamp=d.get("timestamp", ""),
        attempts=d.get("attempts", 1),
        grade=jd.get("grade"),
    )


def main() -> None:
    with open("runs/glm53-v4-goal1-restore.json") as fh:
        g1 = json.load(fh)
    with open("runs/glm53-v4-hardened.json") as fh:
        g2 = json.load(fh)

    objs = []
    seen = set()
    for r in g1["results"] + g2["results"]:
        key = (r["goal"], r["strategy"])
        if key in seen:
            continue
        seen.add(key)
        objs.append(to_result(r))

    merged = build_report(objs, meta={
        "target": "glm-5.3",
        "base_url": "https://ollama.com/v1",
        "judge": "deepseek-v4-flash:0731 (graded rubric)",
        "scope_declaration": "Authorized assessment of own ollama-cloud subscription",
        "hardening": "v4: best_of_n=3, max_retries=3, graded judge, transfer seeding",
    })
    write_reports(
        merged,
        json_path="runs/glm53-v4-final.json",
        html_path="runs/glm53-v4-final.html",
    )
    with open("runs/glm53-v4-final.md", "w", encoding="utf-8") as f:
        f.write(render_markdown_report(merged))
    s = merged["summary"]
    print(f"MERGED: probes={s['total_probes']} hits={s['successful_probes']} "
          f"ASR={s['attack_success_rate']*100:.1f}% "
          f"goals={s['goals_compromised']}/{s['total_goals']} errors={s['errors']}")
    for x in s["by_strategy"][:12]:
        print(f"  {x['strategy']:<38} {x['successes']}/{x['total']}")


if __name__ == "__main__":
    main()
