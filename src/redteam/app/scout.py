"""App recon + scanning — the universal-layer Scout.

Ported harvests:
- infosecn1nja/A-poc: recon→discover→probe phase structure
- Claude-BugHunter: evidence gates (only report what you can prove),
  Verbatim-Repro basis, OWASP 2021 mapping
- Anthropic-Skills: framework alignment (OWASP Top 10 2021 per finding)
- PentAGI: phased recon→exploit flow

Everything zero-dep (urllib). Non-destructive: GET probes only.
"""
from __future__ import annotations

import logging
import re
import urllib.error
import urllib.request
from urllib.parse import urlparse

from redteam.scope import ScopeGuard

log = logging.getLogger(__name__)

SECURITY_HEADERS = {
    "strict-transport-security": "HSTS",
    "content-security-policy": "CSP",
    "x-content-type-options": "XCTO",
    "x-frame-options": "XFO",
    "referrer-policy": "Referrer-Policy",
    "permissions-policy": "Permissions-Policy",
}

PII_PATTERNS = {
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
}
SECRET_PATTERNS = {
    "api_key": re.compile(r"(?:sk[-_][A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|"
                          r"gh[pousr]_[A-Za-z0-9]{30,})"),
}

DEFAULT_WORDLIST = [
    "admin", "administrator", "api", "api/users", "api/users/1",
    "api/admin", "login", "dashboard", ".env", "backup", "config",
    "wp-admin", "phpmyadmin", "server-status", "actuator", "debug",
]

TRAVERSAL_TARGET = "/item/../../../../etc/passwd"
TRAVERSAL_PROOF = re.compile(r"root:[x*]:0:0:", re.IGNORECASE)


class Scout:
    def __init__(self, scope: ScopeGuard, wordlist: list[str] | None = None,
                 traversal_probe: bool = True):
        self.scope = scope
        self.wordlist = wordlist if wordlist is not None else DEFAULT_WORDLIST
        self.traversal_probe = traversal_probe

    def authorize(self, url: str) -> bool:
        return self.scope.authorize_target(url)

    # ------------------------------------------------------------- low level

    def _get(self, url: str, timeout: int = 10) -> tuple[int, dict, bytes]:
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "hermes-redteam"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), (e.read() or b"")
        except Exception as e:  # noqa: BLE001 - network boundary
            log.debug("scout request failed: %s", e)
            return 0, {}, str(e).encode()

    # ------------------------------------------------------------- phases

    def recon(self, base_url: str) -> dict:
        self.authorize(base_url)
        status, headers, body = self._get(base_url)
        hl = {k.lower(): v for k, v in headers.items()}
        missing = [h for h in SECURITY_HEADERS if h not in hl]
        parsed = urlparse(base_url)
        body_text = body.decode("utf-8", errors="replace") if status == 200 else ""
        return {
            "reachable": status > 0,
            "status": status,
            "server_header_present": "server" in hl,
            "server_value": hl.get("server"),
            "powered_by": hl.get("x-powered-by"),
            "security_headers": {
                "present": [h for h in SECURITY_HEADERS if h in hl],
                "missing": missing,
            },
            "tls": {"scheme": parsed.scheme,
                    "is_tls": parsed.scheme == "https"},
            "cookies_flags": self._cookie_flags(hl),
            "title": self._extract_title(body_text) if status == 200 else None,
        }

    def discover(self, base_url: str) -> list[dict]:
        self.authorize(base_url)
        out = []
        for path in self.wordlist:
            url = base_url.rstrip("/") + "/" + path.lstrip("/")
            status, _, _body = self._get(url)
            if status in (200, 201, 301, 302, 401, 403):
                out.append({"path": "/" + path.lstrip("/"), "status": status,
                            "url": url})
        return out

    def probe_traversal(self, base_url: str) -> dict | None:
        if not self.traversal_probe:
            return None
        url = base_url.rstrip("/") + TRAVERSAL_TARGET
        status, _, body = self._get(url)
        text = body.decode("utf-8", errors="replace")
        if status == 200 and (TRAVERSAL_PROOF.search(text)
                              or "root" in text.lower()):
            return {"path": TRAVERSAL_TARGET, "status": status,
                    "evidence": "passwd-like content returned",
                    "snippet": text[:200]}
        return None

    # ------------------------------------------------------------ helpers

    @staticmethod
    def _cookie_flags(headers: dict) -> dict:
        return {n: {"secure": "secure" in v.lower(),
                    "httponly": "httponly" in v.lower(),
                    "samesite": "samesite" in v.lower()}
                for n, v in headers.items() if n.lower() == "set-cookie"}

    @staticmethod
    def _extract_title(body_text: str) -> str | None:
        m = re.search(r"<title>([^<]{1,200})</title>", body_text or "",
                      re.IGNORECASE)
        return m.group(1).strip() if m else None

    # ------------------------------------------------------------- assess

    def assess(self, base_url: str) -> dict:
        """recon + discovery + probes → structured findings."""
        self.authorize(base_url)
        recon = self.recon(base_url)
        findings: list[dict] = []

        # F1: security headers
        missing = recon["security_headers"]["missing"]
        if missing:
            findings.append({
                "id": "SECHEADERS",
                "severity": "medium",
                "owasp": "A05:2021-Security Misconfiguration",
                "title": f"Missing {len(missing)} security headers",
                "evidence": {"missing": missing},
            })

        # F2: TLS
        if not recon["tls"]["is_tls"]:
            findings.append({
                "id": "NO_TLS",
                "severity": "high",
                "owasp": "A02:2021-Cryptographic Failures",
                "title": "Target served over plain HTTP",
                "evidence": {"scheme": "http"},
            })

        # F3: discovery + exposure on each find
        for d in self.discover(base_url):
            path = d["path"].lower()
            if any(k in path for k in ("admin", "dashboard", "wp-admin",
                                       "phpmyadmin", "server-status")) \
                    and d["status"] == 200:
                findings.append({
                    "id": "MISSING_AUTH_ADMIN",
                    "severity": "critical",
                    "owasp": "A01:2021-Broken Access Control",
                    "title": f"Sensitive path reachable without auth: {d['path']}",
                    "evidence": {"path": d["path"], "status": 200},
                })
            _, _, body = self._get(d["url"])
            text = body.decode("utf-8", errors="replace")
            for label, pat in PII_PATTERNS.items():
                m = pat.search(text)
                if m:
                    findings.append({
                        "id": f"PII_{label}",
                        "severity": "critical",
                        "owasp": "A02:2021-Cryptographic Failures",
                        "title": f"Sensitive data ({label}) in response",
                        "evidence": {"path": d["path"],
                                     "sample": m.group(0)[:50]},
                    })
            for label, pat in SECRET_PATTERNS.items():
                sm = pat.search(text)
                if sm:
                    findings.append({
                        "id": f"SECRET_{label}",
                        "severity": "critical",
                        "owasp": "A07:2021-Identification and Auth Failures",
                        "title": f"Secret material ({label}) in response",
                        "evidence": {"path": d["path"],
                                     "sample": sm.group(0)[:8] + "..."},
                    })

        # F5: traversal probe
        trav = self.probe_traversal(base_url)
        if trav:
            findings.append({
                "id": "PATH_TRAVERSAL",
                "severity": "critical",
                "owasp": "A01:2021-Broken Access Control",
                "title": "Path traversal reads system file",
                "evidence": trav,
            })

        return {"recon": recon, "findings": findings}
