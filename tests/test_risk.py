

# ── MITRE ATLAS mapping ────────────────────────────────────────────────────

def test_atlas_maps_injection_to_the_right_subtechnique():
    from redteam.risk import atlas_for

    assert atlas_for("prompt_injection", "prompt_inject")[0] == "AML.T0051.000"
    assert atlas_for("prompt_injection", "indirect_injection")[0] == "AML.T0051.001"


def test_atlas_maps_encoded_payloads_to_adversarial_data():
    from redteam.risk import atlas_for

    assert atlas_for("", "mutate:rot13")[0] == "AML.T0043"
    assert atlas_for("", "obfuscation")[0] == "AML.T0043"


def test_atlas_falls_back_to_jailbreak_for_a_generic_bypass():
    from redteam.risk import atlas_for

    assert atlas_for("", "godmode")[0] == "AML.T0054"


def test_atlas_returns_none_when_it_has_nothing_to_go_on():
    """Better to omit a technique than to publish a wrong ATLAS id."""
    from redteam.risk import atlas_for

    assert atlas_for("", "") is None


def test_every_mapped_atlas_id_is_well_formed():
    import re

    from redteam.risk import (
        ATLAS_ADVERSARIAL_DATA,
        ATLAS_INJECTION_DIRECT,
        ATLAS_INJECTION_INDIRECT,
        ATLAS_JAILBREAK,
        MITRE_ATLAS,
    )

    pairs = [
        *MITRE_ATLAS.values(),
        ATLAS_JAILBREAK, ATLAS_ADVERSARIAL_DATA,
        ATLAS_INJECTION_DIRECT, ATLAS_INJECTION_INDIRECT,
    ]
    for tid, name in pairs:
        assert re.fullmatch(r"AML\.T\d{4}(\.\d{3})?", tid), f"malformed: {tid}"
        assert name and name[0].isupper()


def test_scored_findings_carry_both_taxonomies():
    from redteam.risk import RiskScorer

    f = RiskScorer().rank([{
        "id": "F1", "category": "system_prompt_leakage",
        "strategy": "extraction", "verified": True, "rounds": 2,
    }])[0]
    assert f["owasp_id"] == "LLM07"
    assert f["atlas_id"] == "AML.T0024"
    assert "atlas_technique" in f
