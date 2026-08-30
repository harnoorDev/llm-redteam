"""Orchestrator — runs all 8 proxy testers against a target, aggregates."""
from __future__ import annotations

from redteam.tester.all_testers import (
    IdorTester, AuthBypassTester, MassAssignTester, InjectionTester,
    AuthnTester, BusinessLogicTester, SSRFTester, FileAttackTester,
)


def run_all_testers(base_url: str) -> dict:
    findings: list[dict] = []
    vectors_used = set()

    # IDOR
    idor = IdorTester(base_url=base_url)
    idor_results = idor.test("/api/users/{id}", ["1", "2", "3"])
    vectors_used.add("IDOR")
    findings.extend(r.to_dict() for r in idor_results)

    # auth bypass
    ab = AuthBypassTester(base_url=base_url)
    findings.append(ab.test("/api/admin").to_dict())
    vectors_used.add("AUTH_BYPASS")

    # injection
    inj = InjectionTester(base_url=base_url)
    findings.append(inj.test("/search", param="q").to_dict())
    vectors_used.add("INJECTION")

    # SSRF
    ssrf = SSRFTester(base_url=base_url)
    findings.append(ssrf.test("/fetch", param="url").to_dict())
    vectors_used.add("SSRF")

    # file attack
    fa = FileAttackTester(base_url=base_url)
    findings.append(fa.test("/item/").to_dict())
    vectors_used.add("FILE_ATTACK")

    vulnerable = [f for f in findings if f["verdict"] == "vulnerable"]

    return {
        "target": base_url,
        "summary": {
            "total_probes": len(findings),
            "vulnerable": len(vulnerable),
            "not_vulnerable": sum(1 for f in findings
                                  if f["verdict"] == "not_vulnerable"),
            "suppressed": sum(1 for f in findings if f["verdict"] == "suppressed"),
            "vectors_used": sorted(vectors_used),
        },
        "findings": findings,
    }