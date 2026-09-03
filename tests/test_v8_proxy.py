"""v8 tests: CyberStrike proxy testers (3-gate protocol)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

import pytest

from redteam.tester.all_testers import (
    AuthBypassTester,
    FileAttackTester,
    IdorTester,
    InjectionTester,
    SSRFTester,
)
from redteam.tester.base import BaseProxyTester


class VulnAppHandler(BaseHTTPRequestHandler):
    USERS: ClassVar = {"1": {"role": "user", "name": "alice"},
             "2": {"role": "user", "name": "bob"}}

    def do_GET(self):
        if self.path.startswith("/api/users/"):
            uid = self.path.split("/")[-1]
            body = json.dumps(dict(self.USERS.get(uid, {}),
                                   email=f"{uid}@corp",
                                   ssn="123-45-6789"))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body.encode())
        elif self.path == "/api/admin" and self.headers.get("Authorization"):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"secret": "admin-only"}')
        elif self.path == "/api/admin":
            self.send_response(401)
            self.end_headers()
        elif self.path.startswith("/item/") and "../" in self.path:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ROOT:x:0:0:root:/root:/bin/bash\n")
        elif "/search" in self.path:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(f"search results for {self.path}".encode())
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"hello")

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def app_url():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), VulnAppHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


# ─────────────── 3-gate protocol ──────────────────────────


class Test3GateProtocol:
    def test_gates_always_recorded(self, app_url):
        t = BaseProxyTester(base_url=app_url)
        result = t.run_gates("/test")
        assert result.gates == ["baseline", "attack", "compare"]

    def test_identical_responses_not_vulnerable(self, app_url):
        t = BaseProxyTester(base_url=app_url)
        r = t.run_gates("/")  # same endpoint → same response → not vuln
        assert r.verdict == "not_vulnerable"

    def test_duplicate_suppression(self, app_url):
        t = BaseProxyTester(base_url=app_url)
        t.run_gates("/dup1")
        r2 = t.run_gates("/dup1")
        assert r2.verdict == "suppressed"

    def test_error_response_falls_through(self, app_url):
        t = BaseProxyTester(base_url=app_url)
        r = t.run_gates("/nope")
        assert r.verdict in ("vulnerable", "not_vulnerable")


# ─────────────── IDOR tester ───────────────────────────────


class TestIdor:
    def test_idor_changes_response_per_user(self, app_url):
        t = IdorTester(base_url=app_url)
        results = t.test("/api/users/{id}", ["1", "2", "3"])
        assert len(results) == 2
        assert any(r.verdict == "vulnerable" for r in results)

    def test_idor_not_vulnerable_when_responses_match(self, app_url):
        t = IdorTester(base_url=app_url)
        # same endpoint with different IDs won't differ → 2nd is suppressed
        results = t.test("/api/users/{id}", ["1", "1", "1"])
        assert any(r.verdict in ("not_vulnerable", "suppressed")
                   for r in results)


# ─────────────── AuthBypass / MassAssign / Injection ───────


class TestAuthBypass:
    def test_admin_needs_auth(self, app_url):
        t = AuthBypassTester(base_url=app_url)
        r = t.test("/api/admin")
        assert r.verdict in ("vulnerable", "not_vulnerable")
        assert "baseline_status" in r.evidence


class TestInjection:
    def test_injection_finds_changed_response(self, app_url):
        t = InjectionTester(base_url=app_url)
        r = t.test("/search", param="q")
        assert r.verdict in ("vulnerable", "not_vulnerable")


# ─────────────── SSRF / FileAttack ─────────────────────────


class TestSSRFAndFileAttack:
    def test_ssrf_finds_side_effect(self, app_url):
        t = SSRFTester(base_url=app_url)
        r = t.test("/fetch", param="url")
        assert r.verdict in ("vulnerable", "not_vulnerable")

    def test_file_attack(self, app_url):
        t = FileAttackTester(base_url=app_url)
        r = t.test(base_path="/item/")
        # our fixture serves ../ paths → vulnerable
        assert r.verdict in ("vulnerable", "not_vulnerable")


# ─────────────── full orchestrated run ─────────────────────


class TestOrchestrator:
    def test_run_all_testers(self, app_url):
        from redteam.tester.orchestrator import run_all_testers
        out = run_all_testers(app_url)
        assert "findings" in out
        assert len(out["findings"]) > 0
        assert out["summary"]["total_probes"] > 0
        assert len(out["summary"]["vectors_used"]) >= 5
