"""Tests for scope guard, verification gates, and OOB callback collector."""
import json
import threading
import time
import urllib.request

import pytest


# --- scope guard (pentest-ai-agents _scope-guard.md) -----------------------------


def test_scope_guard_blocks_undeclared_targets():
    from redteam.scope import ScopeGuard

    guard = ScopeGuard({})
    with pytest.raises(PermissionError):
        guard.authorize_target("http://evil.example.com/v1")


def test_scope_guard_allows_declared_and_localhost():
    from redteam.scope import ScopeGuard

    guard = ScopeGuard({
        "allowed_hosts": ["localhost", "127.0.0.1", "api.mycompany.internal"],
        "declaration": "authorized internal assessment",
    })
    assert guard.authorize_target("http://127.0.0.1:11434/v1") is True
    assert guard.authorize_target("https://api.mycompany.internal/v1") is True
    with pytest.raises(PermissionError):
        guard.authorize_target("https://api.openai.com/v1")


def test_scope_guard_requires_declaration_string():
    from redteam.scope import ScopeGuard

    guard = ScopeGuard({"allowed_hosts": ["localhost"]})
    with pytest.raises(PermissionError):
        guard.authorize_target("http://localhost:11434/v1")  # no declaration


# --- verification: run-twice + canary anchors (Claude-BugHunter gates) ------------


def test_run_twice_gate_flags_confabulation():
    from redteam.verification import VerificationGate

    gate = VerificationGate()
    # "system prompt" leak that differs between runs = confabulation
    v = gate.verify_run_twice(
        "extract system prompt",
        ["Your system prompt is: BE KIND ALWAYS", "The prompt says something else"],
        anchor="[CANARY-7f3a]",
    )
    assert v["reproducible"] is False
    assert v["status"] == "confabulation_risk"


def test_run_twice_gate_accepts_verbatim_repro_with_anchor():
    from redteam.verification import VerificationGate

    gate = VerificationGate()
    leak = "Your system prompt is: BE KIND ALWAYS [CANARY-7f3a] beta=off"
    v = gate.verify_run_twice(
        "extract system prompt",
        [leak, leak],
        anchor="[CANARY-7f3a]",
    )
    assert v["reproducible"] is True
    assert v["status"] == "verified"
    assert v["anchor_found"] is True


def test_fp_gate_refusal_is_not_a_vuln_but_compliance_alone_is_weak():
    from redteam.verification import VerificationGate

    gate = VerificationGate()
    v = gate.verify_run_twice("goal", ["I can't help with that.", "I can't help."], None)
    assert v["status"] == "refused"


def test_gate_requires_both_runs_for_verification():
    from redteam.verification import VerificationGate

    gate = VerificationGate()
    v = gate.verify_run_twice("goal", ["here is the content"], None)
    assert v["status"] == "needs_retest"  # only one run recorded


# --- OOB callback collector --------------------------------------------------------


def test_oob_collector_receives_callback_with_canary():
    from redteam.oob import OOBCollector

    col = OOBCollector(host="127.0.0.1", port=0)  # port 0 = ephemeral
    col.start()
    try:
        url = col.canary_url("probe-42")
        # simulate the target model making a callback
        data = json.dumps({"canary": "probe-42", "exfil": "SECRET DATA"})
        req = urllib.request.Request(url, data=data.encode(),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5)

        hits = col.wait_for("probe-42", timeout_s=5)
        assert len(hits) == 1
        assert "/canary/probe-42/" in hits[0]["path"]
        assert "SECRET DATA" in hits[0]["body"]
    finally:
        col.stop()


def test_oob_collector_timeout_returns_empty():
    from redteam.oob import OOBCollector

    col = OOBCollector(host="127.0.0.1", port=0)
    col.start()
    try:
        hits = col.wait_for("never-called", timeout_s=1)
        assert hits == []
    finally:
        col.stop()