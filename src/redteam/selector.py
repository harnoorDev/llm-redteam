"""Adaptive strategy selection — spend the budget where it has worked.

A battery run is `strategies x goals`: 69 strategies against 3 goals is 207
probes, and most of them were never going to land. If a previous run already
showed that `godmode` breaks this model 60% of the time and `direct` never
does, the next run should start from that knowledge instead of rediscovering
it from scratch.

This reads historical outcomes out of finished run reports, ranks strategies
by observed success rate, and picks one at a time until the goal falls or the
attempt budget runs out — turning `strategies x goals` into
`max_attempts x goals`.

Selection is epsilon-greedy rather than pure greedy on purpose. Always playing
the current best strategy means never discovering that a strategy which
happened to fail twice early is actually strong; a fixed exploration rate keeps
the ranking honest as targets change.

Rates are smoothed with Laplace (+1/+2), so a strategy that won its only
attempt scores 0.67 rather than a perfect 1.00 — one observation should not
outrank a strategy with 40 wins in 60 tries.
"""
from __future__ import annotations

import json
import logging
import pathlib
import random

log = logging.getLogger(__name__)

__all__ = ["EpsilonGreedySelector", "StrategyStats"]


class StrategyStats:
    """Per-strategy attempts and successes, mined from past run reports."""

    def __init__(self, stats: dict[str, dict] | None = None):
        self.stats: dict[str, dict] = stats or {}

    # ---- construction -----------------------------------------------------

    @classmethod
    def from_reports(cls, paths, target_model: str | None = None
                     ) -> StrategyStats:
        """Aggregate `by_strategy` blocks from finished run reports.

        `target_model` restricts the history to runs against the same model —
        a strategy's success rate is a property of the target, so mixing
        models produces a ranking that describes neither.
        """
        stats: dict[str, dict] = {}
        for path in paths:
            try:
                with open(path, encoding="utf-8") as f:
                    rep = json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                log.debug("skipping unreadable report %s: %s", path, e)
                continue
            if not isinstance(rep, dict):
                continue
            if target_model and (rep.get("meta") or {}).get(
                    "target") != target_model:
                continue
            for row in (rep.get("summary") or {}).get("by_strategy") or []:
                name = row.get("strategy")
                if not name:
                    continue
                s = stats.setdefault(name, {"attempts": 0, "successes": 0})
                s["attempts"] += int(row.get("total") or 0)
                s["successes"] += int(row.get("successes") or 0)
        return cls(stats)

    @classmethod
    def from_dir(cls, runs_dir: str = "runs",
                 target_model: str | None = None) -> StrategyStats:
        d = pathlib.Path(runs_dir)
        if not d.exists():
            return cls({})
        paths = [p for p in sorted(d.glob("*.json"))
                 if not p.name.startswith((".state-", "coverage-"))
                 and p.name != "attack-memory.json"]
        return cls.from_reports([str(p) for p in paths], target_model)

    # ---- scoring ----------------------------------------------------------

    def rate(self, strategy: str) -> float:
        """Confidence-adjusted success rate; 0.5 for a strategy never tried.

        Scored on the *lower bound* of a Wilson interval, not the raw rate.
        Laplace smoothing is not enough here: it scores a 1-of-1 strategy at
        0.67 and a 40-of-60 strategy at 0.66, so a single lucky win outranks a
        long track record. The Wilson lower bound scores them 0.21 and 0.54,
        which is the ordering you actually want — and it is the same statistic
        this harness uses to decide whether a bypass is real, so selection is
        held to the standard the findings are.
        """
        s = self.stats.get(strategy)
        if not s or not s["attempts"]:
            return 0.5          # unknown, not bad — worth one look
        from redteam.validate import wilson_interval
        low, _high = wilson_interval(s["successes"], s["attempts"])
        return low

    def observed(self, strategy: str) -> tuple[int, int]:
        s = self.stats.get(strategy) or {"successes": 0, "attempts": 0}
        return s["successes"], s["attempts"]

    def ranked(self, candidates: list[str]) -> list[tuple[str, float]]:
        return sorted(((c, self.rate(c)) for c in candidates),
                      key=lambda kv: (-kv[1], kv[0]))

    def record(self, strategy: str, success: bool) -> None:
        """Fold this run's own outcomes in, so selection adapts mid-run."""
        s = self.stats.setdefault(strategy, {"attempts": 0, "successes": 0})
        s["attempts"] += 1
        s["successes"] += int(bool(success))


class EpsilonGreedySelector:
    """Pick the next strategy: usually the best known, sometimes a gamble."""

    def __init__(self, stats: StrategyStats, epsilon: float = 0.2,
                 seed: int | None = None):
        self.stats = stats
        self.epsilon = max(0.0, min(1.0, epsilon))
        self._rng = random.Random(seed)

    def select(self, candidates: list[str], tried: set[str] | None = None
               ) -> str | None:
        """Next strategy to try, or None once every candidate is exhausted."""
        pool = [c for c in candidates if c not in (tried or set())]
        if not pool:
            return None
        if self._rng.random() < self.epsilon:
            return self._rng.choice(pool)          # explore
        return self.stats.ranked(pool)[0][0]       # exploit

    def run_goal(self, goal: str, candidates: list[str], attempt,
                 max_attempts: int = 3) -> dict:
        """Try strategies against one goal until it lands or budget is spent.

        `attempt(goal, strategy)` does the actual probing and returns an object
        with `.success`; it stays injected so this module never touches the
        network and stays trivially testable.
        """
        tried: set[str] = set()
        history: list[dict] = []
        for i in range(max_attempts):
            strategy = self.select(candidates, tried)
            if strategy is None:
                break
            tried.add(strategy)
            prior = self.stats.rate(strategy)
            result = attempt(goal, strategy)
            success = bool(getattr(result, "success", False))
            self.stats.record(strategy, success)
            history.append({
                "attempt": i + 1,
                "strategy": strategy,
                "prior_rate": round(prior, 4),
                "success": success,
            })
            if success:
                return {"goal": goal, "success": True,
                        "attempts": i + 1, "winning_strategy": strategy,
                        "history": history, "result": result}
        return {"goal": goal, "success": False, "attempts": len(history),
                "winning_strategy": None, "history": history,
                "result": history[-1].get("result") if history else None}
