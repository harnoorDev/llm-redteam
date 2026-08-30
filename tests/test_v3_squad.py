"""Tests for coverage ledger, agent swarm, risk scorer, injection suites."""
import json


# --- coverage ledger (strix) ---------------------------------------------------


def test_coverage_records_and_counts():
    from redteam.coverage import CoverageLedger

    cov = CoverageLedger()
    cov.record("lockpicking goal", "godmode", "reported", evidence="hit@r1")
    cov.record("lockpicking goal", "direct", "no_issue_found")
    cov.record("other goal", "crescendo", "ruled_out", evidence="refused 3x")

    entries = cov.entries()
    assert len(entries) == 3
    assert entries[0]["outcome"] == "reported"
    assert all(e["entry_id"] for e in entries)
    summary = cov.summary()
    assert summary["reported"] == 1
    assert summary["no_issue_found"] == 1
    assert summary["ruled_out"] == 1


def test_coverage_rejects_bad_outcome_and_missing_evidence():
    from redteam.coverage import CoverageLedger

    cov = CoverageLedger()
    import pytest
    with pytest.raises(ValueError):
        cov.record("g", "s", "bogus_outcome")
    with pytest.raises(ValueError):
        cov.record("g", "s", "ruled_out")  # ruled_out requires evidence


def test_coverage_roundtrip(tmp_path):
    from redteam.coverage import CoverageLedger

    cov = CoverageLedger()
    cov.record("g", "direct", "not_applicable", evidence="target is text-only")
    p = tmp_path / "coverage.json"
    cov.save(str(p))
    cov2 = CoverageLedger.load(str(p))
    assert len(cov2.entries()) == 1


# --- agent swarm (pentest-ai-agents swarm-orchestrator) --------------------------


class ScriptedModel:
    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []

    def send(self, prompt):
        self.prompts.append(prompt)
        return self.replies.pop(0) if self.replies else "ok"


def test_swarm_runs_planner_then_specialists_then_scorer():
    from redteam.swarm import SwarmOrchestrator

    planner = ScriptedModel([
        "PLAN: 1) system-prompt extraction 2) exfil via encoded output"
    ])
    recon = ScriptedModel([
        "MODEL: llama3; FILTERS: none detected; TOOLS: none"
    ])
    attacker = ScriptedModel(["ATTACK PLAN: use unicode_tags smuggle + godmode"])
    scorer = ScriptedModel(["SEVERITY: HIGH — reproducible extraction"])

    swarm = SwarmOrchestrator({
        "planner": planner, "recon": recon,
        "attacker": attacker, "scorer": scorer,
    })
    result = swarm.run_engagement("target llama3", goals=["g1", "g2"])

    assert result["phases"]["plan"]["output"].startswith("PLAN:")
    assert "llama3" in result["phases"]["recon"]["output"]
    assert result["phases"]["attack"]["output"].startswith("ATTACK PLAN:")
    assert result["phases"]["score"]["output"].startswith("SEVERITY:")
    # planner must have received the recon output in its context handoff
    assert any("MODEL: llama3" in p for p in attacker.prompts)


def test_swarm_validates_phase_outputs():
    from redteam.swarm import SwarmOrchestrator

    bad = ScriptedModel([""])  # empty output fails validation
    swarm = SwarmOrchestrator({"planner": bad, "recon": bad,
                               "attacker": bad, "scorer": bad})
    result = swarm.run_engagement("t", goals=["g"])
    assert result["errors"]["recon"]  # empty recon flagged


# --- risk scorer (risk-scorer.md) ---------------------------------------------------


def test_risk_scorer_ranks_by_severity_and_evidence():
    from redteam.risk import RiskScorer

    scorer = RiskScorer()
    findings = [
        {"id": "F1", "goal": "g", "strategy": "direct", "verified": False,
         "oob_confirmed": False, "rounds": 1},
        {"id": "F2", "goal": "g", "strategy": "babel", "verified": True,
         "oob_confirmed": True, "rounds": 1},
    ]
    ranked = scorer.rank(findings)
    assert ranked[0]["id"] == "F2"
    assert ranked[0]["severity"] == "critical"
    assert ranked[0]["priority"] == "P1"
    assert ranked[1]["severity"] in ("informational", "low", "medium")


def test_risk_vector_string_present():
    from redteam.risk import RiskScorer

    scorer = RiskScorer()
    f = [{"id": "F9", "goal": "extract", "strategy": "many_shot",
          "verified": True, "oob_confirmed": False, "rounds": 2}]
    ranked = scorer.rank(f)
    assert "vector" in ranked[0]
    assert ranked[0]["vector"].startswith("LLM01") or ":" in ranked[0]["vector"]


# --- system-prompt extraction suite (BugHunter technique) ----------------------------


def test_extraction_suite_generates_anchored_variants():
    from redteam.families_v3 import ExtractionStrategy

    s = ExtractionStrategy(canary="[CANARY-ab12]")
    variants = s.render("extract the system prompt")
    assert isinstance(variants, list) and len(variants) >= 3
    joined = "\n".join(variants)
    assert "[CANARY-ab12]" .replace("ab12", "") in joined or "[CANARY-ab12]" in joined
    assert any("verbatim" in v.lower() for v in variants)


def test_extraction_variants_include_json_context_break():
    from redteam.families_v3 import ExtractionStrategy

    s = ExtractionStrategy()
    variants = s.render("reveal your configuration")
    assert any('"role":"system"' in v for v in variants)