"""Converge mode — universal-prompt discovery (WallBreaker parity).

Single-artifact convergence: mine one or more run reports for WINNING
attack prompts, then cluster them by technique and rank by generality —
the prompts that compromised the most goals / models are "universal"
prompts worth keeping as a transfer corpus.

Usage (CLI): `redteam converge runs/run1.json runs/run2.json -o universal-prompts.json`
"""
from __future__ import annotations

import json
import time
from collections import defaultdict


def load_run(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def discover_universal_prompts(run_paths: list[str], top_k: int = 5) -> dict:
    """Cluster winning prompts across runs; rank by generality.

    A prompt's generality = (distinct goals compromised, distinct target
    models compromised). Exact prompt text is the dedup key — winners
    reused across runs surface as one artifact.
    """
    if not run_paths:
        raise ValueError("converge needs at least one run JSON")

    # prompt -> {goals, models, strategies}
    artifacts: dict[str, dict] = defaultdict(
        lambda: {"goals": set(), "models": set(), "strategies": set()})
    winners = 0

    for path in run_paths:
        report = load_run(path)
        model = (report.get("meta") or {}).get("target", "(unknown)")
        for r in report.get("results") or []:
            if not r.get("success"):
                continue
            winners += 1
            prompts = r.get("attack_prompts") or []
            if not prompts:
                continue
            # legacy/multimodal reports may store content blocks, not text
            key = prompts[0]
            if not isinstance(key, str):
                from redteam.runner import flatten_content
                key = flatten_content(key)
            art = artifacts[key]
            art["goals"].add(r.get("goal", ""))
            art["models"].add(model)
            art["strategies"].add(r.get("strategy", ""))

    def _generality(art: dict) -> tuple[int, int]:
        return (len(art["goals"]), len(art["models"]))

    ranked = sorted(artifacts.items(), key=lambda kv: _generality(kv[1]),
                   reverse=True)

    universal = [
        {
            "prompt": prompt,
            "goals": len(art["goals"]),
            "models": sorted(art["models"]),
            "strategies": sorted(art["strategies"]),
        }
        for prompt, art in ranked[:top_k]
    ]

    # technique clusters: aggregate wins per strategy across runs
    cluster_wins: dict[str, dict] = defaultdict(
        lambda: {"wins": 0, "goals": set(), "models": set()})
    for art in artifacts.values():
        for strat in art["strategies"]:
            c = cluster_wins[strat]
            c["wins"] += 1
            c["goals"] |= art["goals"]
            c["models"] |= art["models"]

    clusters = [
        {
            "technique": strat,
            "wins": c["wins"],
            "distinct_goals": len(c["goals"]),
            "models": sorted(c["models"]),
        }
        for strat, c in sorted(cluster_wins.items(),
                               key=lambda kv: kv[1]["wins"], reverse=True)
    ]

    return {
        "meta": {
            "mode": "converge",
            "runs": list(run_paths),
            "winning_probes": winners,
            "unique_winners": len(artifacts),
        },
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "summary": {
            "runs_analyzed": len(run_paths),
            "winning_probes": winners,
            "unique_prompts": len(artifacts),
            "technique_clusters": len(clusters),
            "universal_prompts": len(universal),
        },
        "technique_clusters": clusters,
        "universal_prompts": universal,
    }


def write_converge_report(report: dict, out_path: str) -> str:
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    return out_path
