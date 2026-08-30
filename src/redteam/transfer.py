"""Cross-model transfer seeding: replay winning prompts from prior runs.

Empirically, jailbreak prompts transfer across model families (our llama3
wins landed on GLM). This module mines prior run JSONs for successful
attack prompts and exposes them as `transfer:<strategy>` entries and as
PAIR attacker seeds.
"""
from __future__ import annotations

import json


def load_successes(prior_json: str) -> list[dict]:
    """Extract successful probes: [{goal, strategy, prompt}]."""
    with open(prior_json, "r", encoding="utf-8") as f:
        rep = json.load(f)
    wins = []
    for r in rep.get("results", []):
        if not r.get("success"):
            continue
        prompts = r.get("attack_prompts") or []
        if not prompts:
            tr = r.get("transcript") or []
            prompts = [t.get("attack_prompt", "") for t in tr
                       if t.get("attack_prompt")]
            if not prompts:
                continue
        wins.append({
            "goal": r.get("goal", ""),
            "strategy": r.get("strategy", "unknown"),
            "prompt": prompts[0],
            "reply": (r.get("target_replies") or [""])[0],
        })
    return wins


def transfer_strategies(prior_json: str, goals: list[str],
                        max_per_goal: int = 2) -> list[dict]:
    """Build (goal, transfer:<strategy>) pairs replays can attack with.

    Only goals present in the current target's config are replayed; the
    most successful strategies from the prior run win.
    """
    wins = load_successes(prior_json)
    goal_set = {g.strip().lower() for g in goals}
    per_goal: dict[str, list[dict]] = {}
    for w in wins:
        g = w["goal"].strip().lower()
        if g in goal_set:
            per_goal.setdefault(g, []).append(w)
    out = []
    for g, items in per_goal.items():
        seen = set()
        for w in items[: max_per_goal * 3]:
            if w["strategy"] in seen:
                continue
            seen.add(w["strategy"])
            out.append({
                "goal": w["goal"],
                "strategy": f"transfer:{w['strategy']}",
                "prompt": w["prompt"],
            })
            if len(seen) >= max_per_goal:
                break
    return out


def register_transfer_strategies(prior_json: str, goals: list[str]) -> list[str]:
    """Register transfer:<strategy> families from a prior run.

    Returns the list of registered strategy names to add to the config.
    """
    from redteam.strategies.base import _ensure_loaded, _REGISTRY, Strategy

    _ensure_loaded()
    pairs = transfer_strategies(prior_json, goals)
    names = []

    def _make(name: str, canned: str) -> type[Strategy]:
        class TS(Strategy):
            pass
        TS.name = name
        TS.description = f"Transferred winner from prior run ({name})"
        TS.render = lambda self, goal, _p=canned: _p
        return TS

    for p in pairs:
        name = f"transfer:{p['strategy']}"
        if name in _REGISTRY:
            names.append(name)
            continue
        _REGISTRY[name] = _make(name, p["prompt"])
        names.append(name)
    return names