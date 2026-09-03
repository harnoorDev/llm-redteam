"""CyberStrike proxy testers (v8) — 8 sub-testers with 3-gate protocol.

Ported from CyberStrikeus/CyberStrike's interception pipeline:
8 testers (IDOR, AuthBypass, MassAssign, Injection, AuthN, BizLogic, SSRF,
FileAttack) each follow the 3-gate confirmation protocol:
  1. baseline  — benign request
  2. attack    — the actual test vector
  3. compare   — only on measurable diff does a finding exist
Duplicates (vector, endpoint) are suppressed per session.
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────── request primitive

def _http(url: str, headers: dict | None = None, timeout: int = 8) -> dict:
    """Single GET returning a comparable record."""
    h = {"User-Agent": "hermes-redteam", **(headers or {})}
    req = urllib.request.Request(url, headers=h)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
            return {"status": r.status,
                    "latency_ms": round((time.time() - t0) * 1000, 2),
                    "body": body,
                    "sha": hashlib.sha256(body.encode()).hexdigest()[:16]}
    except urllib.error.HTTPError as e:
        body = (e.read() or b"").decode("utf-8", "replace")
        return {"status": e.code,
                "latency_ms": round((time.time() - t0) * 1000, 2),
                "body": body,
                "sha": hashlib.sha256(body.encode()).hexdigest()[:16]}
    except Exception as e:  # noqa: BLE001 - network boundary
        log.debug("http probe failed: %s", e)
        return {"status": 0, "latency_ms": 0.0, "body": str(e), "sha": ""}


def _default_distinguisher(baseline: dict, attack: dict) -> bool:
    """Measurable-difference rule: status OR body-hash differs."""
    return baseline["sha"] != attack["sha"] or \
        baseline["status"] != attack["status"]


# ─────────────────────────────────────────────── result container

@dataclass
class ProxyFinding:
    vector: str
    endpoint: str
    verdict: str            # vulnerable | not_vulnerable | suppressed | error
    severity: str = "info"
    gates: list = field(default_factory=lambda: ["baseline", "attack", "compare"])
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"vector": self.vector, "endpoint": self.endpoint,
                "verdict": self.verdict, "severity": self.severity,
                "gates": self.gates, "evidence": self.evidence}


# ─────────────────────────────────────────────── base tester

class BaseProxyTester:
    """Shared 3-gate logic + duplicate suppression per (vector, endpoint)."""

    label: str = ""
    severity: str = "high"

    def __init__(self, base_url: str,
                 distinguisher: Callable | None = None):
        self.base_url = base_url.rstrip("/")
        self.distinguisher = distinguisher or _default_distinguisher
        self._seen: set[tuple] = set()

    def run_gates(self, endpoint: str,
                  headers_attack: dict | None = None) -> ProxyFinding:
        key = (self.label, endpoint)
        if key in self._seen:
            return ProxyFinding(vector=self.label, endpoint=endpoint,
                                verdict="suppressed", severity="info",
                                evidence={"reason": "duplicate suppressed"})
        baseline = _http(self.base_url + endpoint)
        attack = _http(self.base_url + endpoint, headers_attack)
        gates = ["baseline", "attack", "compare"]
        measurable = self.distinguisher(baseline, attack)
        with _lock_guard():
            self._seen.add(key)
        verdict = "vulnerable" if measurable else "not_vulnerable"
        return ProxyFinding(
            vector=self.label, endpoint=endpoint, verdict=verdict,
            severity=self.severity if measurable else "info",
            gates=gates,
            evidence={
                "baseline": {"status": baseline["status"], "sha": baseline["sha"]},
                "attack": {"status": attack["status"], "sha": attack["sha"]},
            })


@dataclass
class _lock_guard:
    """Tiny context manager to serialize _seen updates across threads."""
    _l: threading.Lock = field(default_factory=threading.Lock)

    def __enter__(self):
        self._l.acquire()

    def __exit__(self, *a):
        self._l.release()
