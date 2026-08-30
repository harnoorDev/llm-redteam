"""Run state persistence — resume interrupted runs (shannon workspaces +
sliver checkpointing). State is a tiny JSON file of completed (goal, strategy).
"""
from __future__ import annotations

import json
import os
import time


class RunState:
    def __init__(self, run_id: str, goals: list[str], strategies: list[str],
                 done: set[tuple[str, str]] | None = None, path: str | None = None):
        self.run_id = run_id
        self.goals = list(goals)
        self.strategies = list(strategies)
        self.done: set[tuple[str, str]] = done or set()
        self.path = path

    # ------------------------------------------------------------ lifecycle

    @classmethod
    def new(cls, run_id: str, goals: list[str], strategies: list[str],
            state_dir: str = "runs") -> "RunState":
        os.makedirs(state_dir, exist_ok=True)
        path = os.path.join(state_dir, f".state-{run_id}.json")
        return cls(run_id, goals, strategies, path=path)

    @classmethod
    def load(cls, path: str) -> "RunState":
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        done = {(g, s) for g, s in d.get("done", [])}
        return cls(d["run_id"], d["goals"], d["strategies"], done=done, path=path)

    def save(self) -> str:
        if not self.path:
            raise ValueError("state has no path; construct via new()/load()")
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({
                "run_id": self.run_id,
                "goals": self.goals,
                "strategies": self.strategies,
                "done": [list(t) for t in sorted(self.done)],
                "updated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            }, f, indent=1)
        return self.path

    # ------------------------------------------------------------ work math

    def mark_done(self, goal: str, strategy: str) -> None:
        self.done.add((goal, strategy))

    def is_done(self, goal: str, strategy: str) -> bool:
        return (goal, strategy) in self.done

    def remaining_work(self) -> list[tuple[str, str]]:
        return [
            (g, s) for g in self.goals for s in self.strategies
            if (g, s) not in self.done
        ]