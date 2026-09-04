"""Adaptive selection: spend the budget where history says it pays."""
from __future__ import annotations

import json

from redteam.selector import EpsilonGreedySelector, StrategyStats


def _report(tmp_path, name, target, rows, summary_extra=None):
    p = tmp_path / name
    p.write_text(json.dumps({
        "meta": {"target": target},
        "summary": {"by_strategy": rows, **(summary_extra or {})},
        "results": [],
    }), encoding="utf-8")
    return str(p)


# ── mining history ─────────────────────────────────────────────────────────

def test_stats_aggregate_across_reports(tmp_path):
    a = _report(tmp_path, "a.json", "m1", [
        {"strategy": "godmode", "total": 10, "successes": 6},
        {"strategy": "direct", "total": 10, "successes": 0},
    ])
    b = _report(tmp_path, "b.json", "m1", [
        {"strategy": "godmode", "total": 10, "successes": 6},
    ])
    s = StrategyStats.from_reports([a, b])
    assert s.observed("godmode") == (12, 20)
    assert s.observed("direct") == (0, 10)


def test_stats_can_be_scoped_to_one_target_model(tmp_path):
    """A strategy's rate is a property of the target; mixing models is noise."""
    a = _report(tmp_path, "a.json", "model-a",
                [{"strategy": "godmode", "total": 10, "successes": 9}])
    b = _report(tmp_path, "b.json", "model-b",
                [{"strategy": "godmode", "total": 10, "successes": 0}])
    only_a = StrategyStats.from_reports([a, b], target_model="model-a")
    assert only_a.observed("godmode") == (9, 10)
    both = StrategyStats.from_reports([a, b])
    assert both.observed("godmode") == (9, 20)


def test_stats_skip_unreadable_and_non_report_files(tmp_path):
    good = _report(tmp_path, "good.json", "m",
                   [{"strategy": "godmode", "total": 4, "successes": 2}])
    bad = tmp_path / "bad.json"
    bad.write_text("not json at all", encoding="utf-8")
    listy = tmp_path / "listy.json"
    listy.write_text("[1,2,3]", encoding="utf-8")
    s = StrategyStats.from_reports([good, str(bad), str(listy), "missing.json"])
    assert s.observed("godmode") == (2, 4)


def test_from_dir_ignores_sidecar_files(tmp_path):
    _report(tmp_path, "run.json", "m",
            [{"strategy": "godmode", "total": 4, "successes": 4}])
    (tmp_path / ".state-run.json").write_text("{}", encoding="utf-8")
    (tmp_path / "coverage-run.json").write_text("[]", encoding="utf-8")
    (tmp_path / "attack-memory.json").write_text("[]", encoding="utf-8")
    s = StrategyStats.from_dir(str(tmp_path))
    assert s.observed("godmode") == (4, 4)


# ── scoring ────────────────────────────────────────────────────────────────

def test_unknown_strategy_scores_neutral_not_zero():
    """Never tried is not the same as never worked."""
    assert StrategyStats().rate("brand_new") == 0.5


def test_rates_are_confidence_adjusted():
    """One lucky win must not outrank a long track record.

    Laplace smoothing alone fails this: 1-of-1 scores 0.67 and 40-of-60
    scores 0.66. The Wilson lower bound gets the ordering right.
    """
    s = StrategyStats({
        "lucky": {"attempts": 1, "successes": 1},
        "proven": {"attempts": 60, "successes": 40},
    })
    assert s.rate("lucky") < 1.0
    assert s.rate("proven") > s.rate("lucky")


def test_ranking_puts_the_best_strategy_first():
    s = StrategyStats({
        "good": {"attempts": 20, "successes": 15},
        "bad": {"attempts": 20, "successes": 1},
    })
    assert s.ranked(["bad", "good"])[0][0] == "good"


# ── selection ──────────────────────────────────────────────────────────────

def test_greedy_selection_picks_the_historical_best():
    s = StrategyStats({
        "winner": {"attempts": 20, "successes": 18},
        "loser": {"attempts": 20, "successes": 0},
    })
    sel = EpsilonGreedySelector(s, epsilon=0.0, seed=1)
    assert sel.select(["loser", "winner"]) == "winner"


def test_exploration_can_pick_a_non_best_strategy():
    s = StrategyStats({
        "winner": {"attempts": 20, "successes": 18},
        "loser": {"attempts": 20, "successes": 0},
    })
    always_explore = EpsilonGreedySelector(s, epsilon=1.0, seed=7)
    picks = {always_explore.select(["loser", "winner"]) for _ in range(30)}
    assert "loser" in picks, "epsilon=1.0 never explored"


def test_selection_does_not_repeat_a_tried_strategy():
    sel = EpsilonGreedySelector(StrategyStats(), epsilon=0.0, seed=1)
    assert sel.select(["a", "b"], tried={"a"}) == "b"
    assert sel.select(["a", "b"], tried={"a", "b"}) is None


# ── the budget loop ────────────────────────────────────────────────────────

class _Outcome:
    def __init__(self, success):
        self.success = success


def test_run_goal_stops_on_first_success():
    s = StrategyStats({"winner": {"attempts": 10, "successes": 9}})
    sel = EpsilonGreedySelector(s, epsilon=0.0, seed=1)
    calls = []

    def attempt(goal, strategy):
        calls.append(strategy)
        return _Outcome(strategy == "winner")

    out = sel.run_goal("g", ["winner", "other"], attempt, max_attempts=3)
    assert out["success"] is True
    assert out["winning_strategy"] == "winner"
    assert out["attempts"] == 1
    assert calls == ["winner"], "kept probing after a success"


def test_run_goal_respects_the_attempt_budget():
    sel = EpsilonGreedySelector(StrategyStats(), epsilon=0.0, seed=1)
    calls = []

    def attempt(goal, strategy):
        calls.append(strategy)
        return _Outcome(False)

    out = sel.run_goal("g", ["a", "b", "c", "d", "e"], attempt, max_attempts=2)
    assert out["success"] is False
    assert len(calls) == 2, f"budget of 2 but ran {len(calls)}"


def test_run_goal_stops_when_candidates_are_exhausted():
    sel = EpsilonGreedySelector(StrategyStats(), epsilon=0.0, seed=1)
    out = sel.run_goal("g", ["only"], lambda g, s: _Outcome(False),
                       max_attempts=5)
    assert out["attempts"] == 1


def test_outcomes_feed_back_into_selection_within_a_run():
    """A strategy that just failed should lose ground immediately."""
    s = StrategyStats({"a": {"attempts": 2, "successes": 2},
                       "b": {"attempts": 2, "successes": 1}})
    sel = EpsilonGreedySelector(s, epsilon=0.0, seed=1)
    before = s.rate("a")
    sel.run_goal("g", ["a", "b"], lambda g, st: _Outcome(False),
                 max_attempts=1)
    assert s.rate("a") < before


def test_history_records_the_prior_that_drove_each_choice():
    s = StrategyStats({"x": {"attempts": 10, "successes": 5}})
    sel = EpsilonGreedySelector(s, epsilon=0.0, seed=1)
    out = sel.run_goal("g", ["x"], lambda g, st: _Outcome(True),
                       max_attempts=1)
    step = out["history"][0]
    assert step["strategy"] == "x"
    assert 0.0 <= step["prior_rate"] <= 1.0
    assert step["success"] is True
