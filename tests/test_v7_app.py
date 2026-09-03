"""v7 tests: universal app red-team layer (PentAGI/Sliver/BugHunter harvest).

Scope: any HTTP app (web/API), not just LLMs. Built-in passive + safe
active checks with zero external deps; optional native-tool drivers
(nmap/nuclei/etc) auto-detected from PATH. All behind the ScopeGuard.
"""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

# --- test app: deliberately vulnerable endpoints -------------------------------

class VulnHandler(BaseHTTPRequestHandler):
    def _hdrs(self):
        return {k.lower(): v for k, v in self.headers.items()}

    def do_GET(self):
        h = self._hdrs()
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body>Welcome to ShopNow</body></html>")
        elif self.path == "/admin":
            # missing auth, missing TLS redirect, missing headers demo
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<html>ADMIN PANEL - user list: admin/admin123</html>")
        elif self.path.startswith("/item/") and "../" in self.path:
            # path traversal echo
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ROOT:x:0:0:root:/root:/bin/bash\n")
        elif self.path == "/api/users/1" or self.path == "/api/users/2":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(
                {"id": self.path[-1], "ssn": "123-45-6789"}).encode())
        elif self.path == "/api/admin":
            # IDOR demo: returns unauthorized data without auth header
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"api_key": "sk-abc123", "ssn": "999-99-9999"}')
        elif self.path == "/redirect":
            # open redirect
            loc = "https://evil.example/" if "evil" in self.path else "/"
            self.send_response(302)
            self.send_header("Location", loc)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def app_url():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), VulnHandler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


# --- guard integration ----------------------------------------------------------

def test_app_checks_respect_scope_guard():
    from redteam.app.scout import Scout
    from redteam.scope import ScopeGuard

    guard = ScopeGuard({"allowed_hosts": ["127.0.0.1"],
                        "declaration": "local test"})
    s = Scout(scope=guard)
    s.authorize("http://127.0.0.1:8080")  # no exception
    with pytest.raises(PermissionError):
        s.authorize("http://evil.example.com")


# --- recon phase (httpx/curl/python fallthrough, always works) -------------------

def test_scout_recon_headers_and_tls(app_url):
    from redteam.app.scout import Scout
    from redteam.scope import ScopeGuard

    guard = ScopeGuard({"allowed_hosts": ["127.0.0.1"],
                        "declaration": "local test"})
    s = Scout(scope=guard)
    rec = s.recon(app_url)
    assert rec["reachable"] is True
    assert rec["status"] in (200, 301, 302, 404)
    assert rec["server_header_present"] in (True, False)
    assert "security_headers" in rec
    missing = rec["security_headers"]["missing"]
    assert "strict-transport-security" in missing
    assert "x-frame-options" in missing
    assert rec["tls"]["scheme"] == "http"


def test_scout_discovers_common_paths(app_url):
    from redteam.app.scout import Scout
    from redteam.scope import ScopeGuard

    guard = ScopeGuard({"allowed_hosts": ["127.0.0.1"],
                        "declaration": "local test"})
    s = Scout(scope=guard, wordlist=["admin", "api/users/1", "nope"])
    finds = s.discover(app_url)
    assert any(f["path"] == "/admin" and f["status"] == 200
               for f in finds)
    assert not any(f["status"] == 404 and f["path"] == "/nope" for f in finds)


# --- findings -----------------------------------------------------------------


def test_scanner_flags_missing_auth_and_headers(app_url):
    from redteam.app.scout import Scout
    from redteam.scope import ScopeGuard

    guard = ScopeGuard({"allowed_hosts": ["127.0.0.1"],
                        "declaration": "local test"})
    s = Scout(scope=guard, wordlist=["admin"])
    rep = s.assess(app_url)
    findings = rep["findings"]
    ids = [f["id"] for f in findings]
    assert "MISSING_AUTH_ADMIN" in "".join(ids) or any(
        "admin" in f.get("evidence", {}).get("path", "") for f in findings)
    headers_f = [f for f in findings if f["id"].startswith("SECHEADERS")]
    assert headers_f, "security headers finding expected"
    # OWASP mapping present (Anthropic-skills/risks scorer alignment)
    assert all(f.get("owasp") for f in findings)


def test_scanner_flags_sensitive_data_exposure(app_url):

    from redteam.app.scout import Scout
    from redteam.scope import ScopeGuard

    guard = ScopeGuard({"allowed_hosts": ["127.0.0.1"],
                        "declaration": "local test"})
    s = Scout(scope=guard, wordlist=["api/users/1"])
    rep = s.assess(app_url)
    exposure = [f for f in rep["findings"] if "PII" in f["id"]
                or "api_key" in json.dumps(f.get("evidence", {}))]
    assert exposure, "SSN/API-key exposure should be flagged"


def test_scanner_flags_path_traversal(app_url):
    from redteam.app.scout import Scout
    from redteam.scope import ScopeGuard

    guard = ScopeGuard({"allowed_hosts": ["127.0.0.1"],
                        "declaration": "local test"})
    s = Scout(scope=guard, wordlist=[], traversal_probe=True)
    rep = s.assess(app_url)
    trav = [f for f in rep["findings"] if "TRAV" in f["id"]]
    assert trav and "root" in json.dumps(trav[0].get("evidence", {})).lower()


# --- native tool drivers (skip gracefully when absent) --------------------------


def test_registry_lists_and_runs_httpx_driver(app_url):
    from redteam.app.tools import ToolRegistry

    reg = ToolRegistry()
    assert "curl" in reg.available()   # curl is on this box
    out = reg.run("curl", [app_url, "-s", "-o", os.devnull,
                           "-w", "%{http_code}"])
    assert out["returncode"] == 0
    assert out["stdout"].strip() in ("200", "301", "302", "404")


def test_registry_missing_tool_is_not_fatal():
    from redteam.app.tools import ToolRegistry

    reg = ToolRegistry()
    assert reg.available("definitely-not-installed-xyz") is False
    res = reg.run("definitely-not-installed-xyz", ["--x"])
    assert res["available"] is False


# --- app campaign (phased like the LLM campaign) --------------------------------


def test_app_campaign_runs_and_reports(app_url):
    from redteam.app.campaign import AppCampaign
    from redteam.scope import ScopeGuard

    guard = ScopeGuard({"allowed_hosts": ["127.0.0.1"],
                        "declaration": "local test"})
    camp = AppCampaign(scope=guard, target=app_url)
    report = camp.run()
    assert report["meta"]["target"] == app_url
    assert report["summary"]["total_probes"] > 0
    assert any(f["severity"] != "info" for f in report["findings"])
    # coverage + memory hooks
    assert len(report["coverage"]) == report["summary"]["total_probes"]
    # markdown report generated
    assert report["artifacts"]["md"].endswith(".md")
    assert report["artifacts"]["html"].endswith(".html")
