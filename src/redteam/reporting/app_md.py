"""App-campaign markdown report (shannon-style: findings + OWASP + coverage)."""
from __future__ import annotations


def _esc(s) -> str:
    return str(s or "").replace("|", "\\|").replace("\n", " ")


def render_app_markdown(report: dict) -> str:
    meta = report["meta"]
    s = report["summary"]
    lines = [
        "# App Red-Team Engagement Report",
        "",
        f"*Generated {report['generated_at']}*",
        "",
        "## Engagement Details",
        "",
        f"- **Target:** {meta['target']}",
        f"- **Scope Declaration:** {meta['scope_declaration']}",
        f"- **Mode:** {meta['mode']}",
        "",
        "## Executive Summary",
        "",
        f"- **{s['findings_count']} findings** "
        f"(critical: {s['critical']}, high: {s['high']}, "
        f"medium: {s['medium']}) across {s['total_probes']} probes.",
        "",
        "## Findings",
        "",
    ]
    findings = report.get("findings") or []
    if findings:
        lines.append("| ID | Severity | OWASP 2021 | Title |")
        lines.append("|---|---|---|---|")
        for f in findings:
            lines.append(
                f"| {_esc(f['id'])} | {f['severity']} "
                f"| {_esc(f.get('owasp', ''))} | {_esc(f['title'])} |")
    else:
        lines.append("_No findings recorded._")
    lines += ["", "## Coverage", "",
              f"- {s['total_probes']} probes executed "
              "(recon + discovery + active probes)", ""]
    recon = report.get("recon") or {}
    if recon:
        lines += [
            "## Recon",
            "",
            f"- Status: **{recon.get('status')}** "
            f"({'reachable' if recon.get('reachable') else 'unreachable'})",
            f"- Scheme: {recon.get('tls', {}).get('scheme', '?')}",
            f"- Missing security headers: "
            f"{', '.join(recon.get('security_headers', {}).get('missing', [])) or 'none'}",
            "",
        ]
    lines += [
        "## Methodology",
        "",
        "- Phase flow: recon → path discovery → targeted probes "
        "(BugHunter-style evidence gates; only report what you can prove).",
        "- OWASP Top 10 (2021) mapping on every finding "
        "(Anthropic-skills alignment).",
        "- Zero destructive payloads: GET probes + read-only traversal proof "
        "only; no injection, no brute force, no DoS.",
        "- Native tools are enumerated but never required "
        "(www PentAGI-style drivers optional).",
        "",
        "## Limitations",
        "",
        "- Single-PoV finding confidence: rerun against staged hosts or with "
        "-_-run-twice to reduce FP.",
        "- No XSS/RCE/SQLi payloads in this pass; those need explicit "
        "authorized-engagement gates and are not enabled by default.",
    ]
    return "\n".join(lines)