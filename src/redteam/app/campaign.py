"""App campaign — phased scan for any HTTP app (PentAGI flow mapping).

phases: recon → discover → probe (findings) → (optional) native tools.
Artifacts: JSON + HTML + MD like the LLM campaigns. Coverage ledger records
each probe for provenance (strix-style).
"""
from __future__ import annotations

import json
import os
import time

from redteam.app.tools import ToolRegistry
from redteam.scope import ScopeGuard


class AppCampaign:
    def __init__(self, scope: ScopeGuard, target: str,
                 wordlist: list[str] | None = None,
                 out_dir: str = "runs", run_name: str | None = None,
                 tools: ToolRegistry | None = None):
        self.scope = scope
        self.target = target
        self.wordlist = wordlist or []
        self.out_dir = out_dir
        self._run_name = run_name or time.strftime("app-%Y%m%d-%H%M%S")
        self.registry = tools or ToolRegistry()

    def run_name(self) -> str:
        return self._run_name

    def run(self) -> dict:
        from redteam.app.scout import Scout

        os.makedirs(self.out_dir, exist_ok=True)
        scout = Scout(scope=self.scope, wordlist=self.wordlist)
        coverage: list[dict] = []

        recon = scout.recon(self.target)
        coverage.append({"phase": "recon", "target": self.target,
                         "status": recon["status"]})

        findings: list[dict] = []
        if recon["reachable"]:
            assessed = scout.assess(self.target)
            findings = assessed["findings"]
            for f in findings:
                coverage.append({"phase": "probe",
                                 "id": f["id"],
                                 "severity": f["severity"]})

        accepted = [f for f in findings
                    if f.get("severity") in ("critical", "high", "medium")]

        report = {
            "meta": {
                "mode": "app-campaign",
                "target": self.target,
                "scope_declaration": self.scope.describe()["declaration"],
                "native_tools": {
                    t: self.registry.available(t)
                    for t in ("nmap", "httpx", "nuclei", "nikto", "whatweb")
                },
            },
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "summary": {
                "total_probes": len(coverage),
                "findings_count": len(findings),
                "critical": sum(1 for f in accepted
                                if f["severity"] == "critical"),
                "high": sum(1 for f in accepted if f["severity"] == "high"),
                "medium": sum(1 for f in accepted if f["severity"] == "medium"),
            },
            "findings": findings,
            "recon": recon,
            "coverage": coverage,
            "artifacts": {},
        }

        base = os.path.join(self.out_dir, self.run_name())
        json_path = base + ".json"
        html_path = base + ".html"
        md_path = base + ".md"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=1)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(self._render_html(report))
        from redteam.reporting.app_md import render_app_markdown
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(render_app_markdown(report))
        report["artifacts"] = {"json": json_path, "html": html_path,
                               "md": md_path}
        return report

    # ------------------------------------------------------------ rendering

    # ------------------------------------------------------------ rendering

    @staticmethod
    def _render_html(report: dict) -> str:
        from html import escape
        rows = "".join(
            f"<tr><td class='mono'>{escape(f['id'])}</td>"
            f"<td class='{f['severity']}'>{f['severity']}</td>"
            f"<td>{escape(f['owasp'])}</td><td>{escape(str(f['title']))}</td>"
            f"</tr>"
            for f in report["findings"])
        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>App Red-Team Report</title>
<style>
 body {{ font-family: sans-serif; margin: 2rem; background: #0f1117;
        color: #e6e6e6; }}
 table {{ border-collapse: collapse; width: 100%; }}
 th, td {{ border-bottom: 1px solid #23273a; padding: .5rem; text-align: left; }}
 th {{ color: #9aa3c0 }} .critical {{ color: #ef4444; font-weight: 700 }}
 .high {{ color: #f97316 }} .medium {{ color: #f59e0b }}
 .low, .info {{ color: #9aa3c0 }} .mono {{ font-family: Menlo, monospace }}
</style></head><body>
<h1>App Red-Team Report</h1>
<p>{escape(report['meta']['target'])} · {report['generated_at']}</p>
<div class="cards">
  <div>Critical: <b>{report['summary']['critical']}</b></div>
  <div>High: <b>{report['summary']['high']}</b></div>
  <div>Medium: <b>{report['summary']['medium']}</b></div>
</div>
<h2>Findings</h2>
<table><tr><th>ID</th><th>Severity</th><th>OWASP</th><th>Title</th></tr>
{rows}</table>
</body></html>"""

    def _render_md(self, report: dict) -> str:
        from redteam.reporting.app_md import render_app_markdown
        return render_app_markdown(report)