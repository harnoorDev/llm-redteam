"""Markdown engagement report — ported from KeygraphHQ/shannon sample reports
(executive summary, findings with severity+OWASP, coverage, methodology).
"""
from __future__ import annotations

from redteam.risk import RiskScorer


def _esc(s) -> str:
    return str(s or "").replace("|", "\\|").replace("\n", " ")


def render_markdown_report(report: dict) -> str:
    meta = report.get("meta", {})
    s = report.get("summary", {})
    results = report.get("results", [])
    rate = (s.get("attack_success_rate") or 0) * 100

    lines: list[str] = []
    lines.append("# LLM Red-Team Engagement Report")
    lines.append("")
    lines.append(f"*Generated {report.get('generated_at', '')}*")
    lines.append("")
    lines.append("## Engagement Details")
    lines.append("")
    for k in ("target", "base_url", "scope_declaration"):
        if meta.get(k):
            label = k.replace("_", " ").title()
            lines.append(f"- **{label}:** {meta[k]}")
    lines.append("")

    # ---------------------------------------------------------- exec summary
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(
        f"- {s.get('total_probes', 0)} probes executed across "
        f"{s.get('total_goals', 0)} goal(s); attack success rate "
        f"**{rate:.1f}%** ({s.get('successful_probes', 0)} hits)."
    )
    lines.append(
        f"- **{s.get('goals_compromised', 0)}/{s.get('total_goals', 0)}** "
        f"goals compromised; {s.get('errors', 0)} probe errors."
    )
    lines.append("")

    # ------------------------------------------------------------- findings
    lines.append("## Findings")
    lines.append("")
    successful = [r for r in results if r.get("success")]
    if successful:
        ranked = RiskScorer().rank([
            {
                "id": f"F{ i + 1:02d}",
                "goal": r.get("goal"),
                "strategy": r.get("strategy"),
                "verified": bool(r.get("verified", r.get("judge", {}).get(
                    "method") == "llm_judge")),
                "oob_confirmed": bool(r.get("oob_confirmed")),
                "rounds": r.get("turns", r.get("rounds", 1)),
            }
            for i, r in enumerate(successful)
        ])
        lines.append("| ID | Severity | OWASP | Goal | Strategy | Evidence |")
        lines.append("|---|---|---|---|---|---|")
        for f in ranked:
            lines.append(
                f"| {f['id']} | {f['severity']} | {f['owasp_id']} "
                f"| {_esc(f['goal'])[:80]} | {_esc(f['strategy'])} "
                f"| {_esc(f['vector'])} |"
            )
        lines.append("")
        lines.append("**Reproduction:** for each finding, the exact prompt and "
                     "full reply are in the run JSON (`results[].attack_prompts` / "
                     "`results[].target_replies`). Re-run with `verification."
                     "run_twice: true` to attach verbatim-reproducibility proof.")
    else:
        lines.append("_No successful attacks recorded._")
    lines.append("")

    # ------------------------------------------------------------- coverage
    lines.append("## Coverage")
    lines.append("")
    lines.append("| Strategy | Hits / Probes | Rate |")
    lines.append("|---|---|---|")
    for b in s.get("by_strategy", []):
        lines.append(
            f"| {_esc(b['strategy'])} | {b['successes']}/{b['total']} "
            f"| {b['rate'] * 100:.0f}% |"
        )
    lines.append("")
    lines.append(
        "_Coverage answers what was looked at and how each probe closed; "
        "per-probe transcripts (including misses) are in the run JSON._"
    )
    lines.append("")

    # ----------------------------------------------------------- methodology
    lines.append("## Methodology")
    lines.append("")
    lines.append(
        "- Probes: each (goal, strategy) pair sends the crafted prompt to the "
        "target; multi-turn families replay scripted escalation turns."
    )
    lines.append(
        "- Judging: hybrid — regex refusal heuristics, goal-verbatim check, "
        "then LLM-as-judge; judge model and prompts are recorded in the JSON."
    )
    lines.append(
        "- Verification (Claude-BugHunter gates): findings marked `verified` "
        "reproduced verbatim across two fresh runs anchored on a non-guessable "
        "canary; exfil findings require an OOB callback at the canary URL. "
        "Confabulation is not a finding."
    )
    lines.append(
        "- Severity by impact, not novelty (risk-scorer honesty rule); OWASP "
        "LLM Top 10 (2025) IDs anchor each finding."
    )
    lines.append("")
    lines.append("## Limitations")
    lines.append("")
    lines.append(
        "- Non-determinism: single-run compliance without verification is "
        "reported as informational."
    )
    lines.append(
        "- Model-level jailbreak content is NOT a vulnerability by itself; "
        "impact requires a trust boundary crossing (tool, data, tenant)."
    )
    return "\n".join(lines)