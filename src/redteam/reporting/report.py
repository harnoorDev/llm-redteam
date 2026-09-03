"""Aggregate run results into a report; render JSON and HTML."""
from __future__ import annotations

import html as _html
import json
import time


def build_report(results: list, meta: dict | None = None) -> dict:
    total = len(results)
    successes = sum(1 for r in results if r.success)
    goals = sorted({r.goal for r in results})
    strategies = sorted({r.strategy for r in results})

    by_strategy = []
    for s in strategies:
        subset = [r for r in results if r.strategy == s]
        wins = sum(1 for r in subset if r.success)
        by_strategy.append({
            "strategy": s,
            "total": len(subset),
            "successes": wins,
            "rate": round(wins / len(subset), 4) if subset else 0.0,
        })
    by_strategy.sort(key=lambda x: (-x["successes"], x["strategy"]))

    by_goal = []
    for g in goals:
        subset = [r for r in results if r.goal == g]
        wins = sum(1 for r in subset if r.success)
        by_goal.append({
            "goal": g,
            "total": len(subset),
            "successes": wins,
            "compromised": wins > 0,
        })

    return {
        "meta": dict(meta or {}),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "summary": {
            "total_probes": total,
            "successful_probes": successes,
            "attack_success_rate": round(successes / total, 4) if total else 0.0,
            "total_goals": len(goals),
            "goals_compromised": sum(1 for g in by_goal if g["compromised"]),
            "errors": sum(1 for r in results if r.error),
            "by_strategy": by_strategy,
            "by_goal": by_goal,
        },
        "results": [r.to_dict() for r in results],
    }


def write_reports(report: dict, json_path: str | None, html_path: str | None) -> None:
    if json_path:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
    if html_path:
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(render_html(report))


def _esc(x) -> str:
    return _html.escape(str(x), quote=True)


def render_html(report: dict) -> str:
    s = report["summary"]
    rate = s["attack_success_rate"] * 100
    rows = []
    for r in report["results"]:
        badge = (
            '<span class="ok">SUCCESS</span>' if r["success"]
            else '<span class="err">refused</span>'
        )
        if r.get("error"):
            badge = '<span class="warn">error</span>'
        if "attack_prompts" in r:      # standard run: per-probe row
            strat = r["strategy"]
            goal = (r["goal"] or "")[:160]
            turns = r["turns"]
            first_reply = (r["target_replies"] or [""])[0][:120]
            judge_method = r["judge"].get("method") if r.get("judge") else ""
        else:                           # PAIR run: iterative outcome row
            strat = f"PAIR ({r.get('rounds', '?')} rounds)"
            goal = (r.get("goal") or "")[:160]
            turns = r.get("rounds", 0)
            tr = r.get("transcript") or [{}]
            first_reply = (tr[-1].get("target_reply") or "")[:120]
            judge_method = tr[-1].get("judge_method", "")
        rows.append(f"""
        <tr>
          <td class="mono">{_esc(strat)}</td>
          <td>{_esc(goal)}</td>
          <td class="center">{turns}</td>
          <td class="center">{badge}</td>
          <td class="mono small">{_esc(first_reply)}</td>
          <td class="mono small">{_esc(judge_method)}</td>
        </tr>""")

    strat_rows = "".join(
        f"<tr><td class='mono'>{_esc(x['strategy'])}</td>"
        f"<td class='center'>{x['successes']}/{x['total']}</td>"
        f"<td class='center'>{x['rate']*100:.1f}%</td></tr>"
        for x in s["by_strategy"]
    )
    goal_rows = "".join(
        f"<tr><td>{_esc(g['goal'][:120])}</td>"
        f"<td class='center'>{'YES' if g['compromised'] else 'no'}</td>"
        f"<td class='center'>{g['successes']}/{g['total']}</td></tr>"
        for g in s["by_goal"]
    )
    m = report.get("meta", {})
    meta_bits = " &middot; ".join(
        f"{_esc(k)}: <b>{_esc(v)}</b>" for k, v in m.items()
    ) or "&mdash;"

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>LLM Red Team Report</title>
<style>
  body {{ font-family: -apple-system, 'Segoe UI', sans-serif; margin: 2rem;
         background: #0f1117; color: #e6e6e6; }}
  h1 {{ font-size: 1.4rem; }} h2 {{ font-size: 1.1rem; margin-top: 2rem; }}
  .cards {{ display: flex; gap: 1rem; flex-wrap: wrap; }}
  .card {{ background: #1a1d27; border: 1px solid #2a2e3f; border-radius: 10px;
          padding: 1rem 1.4rem; min-width: 140px; }}
  .card .num {{ font-size: 1.8rem; font-weight: 700; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: .6rem;
          background: #14161f; border-radius: 8px; overflow: hidden; }}
  th, td {{ text-align: left; padding: .5rem .7rem; border-bottom: 1px solid #23273a;
           font-size: .85rem; vertical-align: top; }}
  th {{ background: #1a1d27; color: #9aa3c0; text-transform: uppercase;
       font-size: .7rem; letter-spacing: .06em; }}
  .center {{ text-align: center; }} .mono {{ font-family: ui-monospace, Menlo, monospace; }}
  .small {{ font-size: .75rem; color: #9aa3c0; }}
  .ok {{ color: #22c55e; font-weight: 700; }} .err {{ color: #ef4444; }}
  .warn {{ color: #f59e0b; }}
  .meta {{ color: #9aa3c0; font-size: .85rem; }}
</style></head>
<body>
<h1>LLM Red-Team Report</h1>
<p class="meta">{report['generated_at']} &middot; {meta_bits}</p>

<div class="cards">
  <div class="card"><div class="num">{s['total_probes']}</div>probes</div>
  <div class="card"><div class="num">{s['successful_probes']}</div>successful attacks</div>
  <div class="card"><div class="num">{rate:.1f}%</div>Attack success rate</div>
  <div class="card"><div class="num">{s['goals_compromised']}/{s['total_goals']}</div>goals compromised</div>
  <div class="card"><div class="num">{s['errors']}</div>errors</div>
</div>

<h2>By strategy</h2>
<table><tr><th>Strategy</th><th>Successes</th><th>Rate</th></tr>{strat_rows}</table>

<h2>By goal</h2>
<table><tr><th>Goal</th><th>Compromised</th><th>Successes</th></tr>{goal_rows}</table>

<h2>Per-probe detail</h2>
<table>
<tr><th>Strategy</th><th>Goal</th><th>Turns</th><th>Outcome</th>
<th>First reply (truncated)</th><th>Judge</th></tr>
{''.join(rows)}
</table>
</body></html>"""
