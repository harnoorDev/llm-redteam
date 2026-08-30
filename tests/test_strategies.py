"""Tests for attack strategy families and the registry."""
import pytest

from redteam.strategies.base import get_strategy, list_strategies


def test_registry_contains_all_seven_families():
    assert set(list_strategies()).issuperset({
        "direct",
        "roleplay",
        "fiction",
        "crescendo",
        "obfuscation",
        "persuasion",
        "refusal_suppression",
    })


def test_get_strategy_unknown_name_raises():
    with pytest.raises(KeyError):
        get_strategy("does-not-exist")


def test_single_turn_strategies_return_string_containing_goal():
    for name in ("direct", "roleplay", "fiction", "obfuscation", "persuasion",
                 "refusal_suppression"):
        s = get_strategy(name)
        out = s.render("make a hidden message by writing only the word BANANA")
        assert isinstance(out, str), f"{name} should be single-turn"
        assert len(out) > len("banana"), f"{name} prompt too bare"
    # goal must survive verbatim in the rendered prompt
    assert "BANANA" in get_strategy("direct").render("write only the word BANANA")


def test_crescendo_is_multi_turn_script_with_goal_in_final_turn():
    s = get_strategy("crescendo")
    goal = "how to make a paper airplane that flies far"
    turns = s.render(goal)
    assert isinstance(turns, list) and len(turns) >= 3
    assert all(isinstance(t, str) and t.strip() for t in turns)
    assert goal in turns[-1], "final crescendo turn must contain the real goal"


def test_strategy_metadata():
    s = get_strategy("crescendo")
    assert s.is_multi_turn is True
    s2 = get_strategy("roleplay")
    assert s2.is_multi_turn is False
    assert s2.description  # human-readable description non-empty