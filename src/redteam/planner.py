"""Campaign planner + executor — ported from vxcontrol/pentagi's flow/task/
subtask decomposition and task_assignment_wrapper.

A campaign is the full engagement for one goal: cheap reconnaissance probes
first, then the main battery, then adaptive escalation (mentor/refine), and
finally evolutionary breeding with leftover budget. The executor early-exits
the moment full compliance lands.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class CampaignPlanner:
    """Static planner: staged phases with budgets. Memory-aware."""

    def __init__(self, memory=None, target_model: str | None = None):
        self.memory = memory
        self.target_model = target_model

    def default_phases(self) -> int:
        return 4

    def plan(self, goal: str, budget: int = 12) -> dict:
        budget = max(6, int(budget))
        recon = max(2, budget // 6)
        battery = max(3, budget // 2)
        adapt = max(2, budget // 4)
        evolve = max(1, budget - recon - battery - adapt)

        return {
            "goal": goal,
            "budget": budget,
            "phases": [
                {"phase": "recon", "budget": recon,
                 "note": "probe target defenses cheaply",
                 "strategies": ["direct"]},
                {"phase": "battery", "budget": battery,
                 "note": "main arsenal, memory winners first",
                 "strategies": self._battery_order(goal)},
                {"phase": "adapt", "budget": adapt,
                 "note": "mentor-directed switch + spec escalation on partials",
                 "strategies": []},  # filled adaptively by the executor
                {"phase": "evolve", "budget": evolve,
                 "note": "evolutionary breeding with remaining budget",
                 "strategies": []},
            ],
        }

    def _battery_order(self, goal: str) -> list[str]:
        base = [
            "command_protocol", "dataset_seed", "prompt_inject",
            "token_spoof", "many_shot", "babel", "system_shadow",
            "mutate:a1z26", "mutate:unicode_tags",
            "godmode+mutate:leetspeak",
        ]
        if self.memory is None:
            return base
        try:
            hits = self.memory.recall(
                f"{self.target_model or ''} {goal}", limit=2)
        except Exception as e:  # noqa: BLE001 - memory backend must not break planning
            log.debug("memory recall failed: %s", e)
            return base
        winners = [h["strategy"] for h in hits if h.get("grade") == "full"]
        return list(dict.fromkeys(winners + base))


class CampaignExecutor:
    """Runs a planned campaign phase-by-phase with early exit on success."""

    def __init__(self, runner, planner: CampaignPlanner, memory=None,
                 mentor=None, evolver_factory=None):
        self.runner = runner
        self.planner = planner
        self.memory = memory
        self.mentor = mentor
        self.evolver_factory = evolver_factory

    def execute(self, goal: str, budget: int = 12) -> dict:
        plan = self.planner.plan(goal, budget=budget)
        phases_run: list[dict] = []
        spent = 0
        best_fitness = 0.0
        success = False
        results: list = []

        for phase in plan["phases"]:
            name = phase["phase"]
            phase_budget = int(phase["budget"])

            if name == "evolve":
                if self.evolver_factory is None:
                    continue
                evolver = self.evolver_factory()
                outcome = evolver.run(goal)
                phases_run.append({
                    "phase": name, "budget": phase_budget,
                    "outcome": {
                        "success": outcome["success"],
                        "generations": outcome["generations"],
                        "best_fitness": outcome["best_fitness"],
                        "best_prompt": outcome.get("best_prompt", ""),
                    },
                })
                spent += phase_budget
                best_fitness = max(best_fitness,
                                   float(outcome.get("best_fitness") or 0.0))
                if outcome["success"]:
                    success = True
                    results.append({
                        "goal": goal, "strategy": "evolve",
                        "success": True, "turns": outcome["generations"],
                        "attack_prompts": [outcome.get("best_prompt", "")],
                        "target_replies": [outcome.get("best_reply", "")],
                        "judge": {"success": True, "method": "evolve",
                                  "raw": "", "grade": "full"},
                        "error": None, "duration_s": 0.0,
                        "timestamp": "", "attempts": 1, "grade": "full",
                    })
                break

            if name == "adapt":
                strategies = self._adapt_strategies(results)[:phase_budget]
            else:
                strategies = list(phase["strategies"])[:phase_budget]

            if not strategies:
                continue

            phase_results = self.runner.run_goal(goal, strategies)
            phases_run.append({"phase": name, "strategies": strategies,
                               "budget": phase_budget})
            results.extend(phase_results)
            spent += len(strategies)

            for r in phase_results:
                best_fitness = max(best_fitness, self._fitness(r))
            if any(getattr(r, "success", False) for r in phase_results):
                success = True
                break

        if not isinstance(phases_run, list) or not phases_run:
            phases_run = []
        return {
            "goal": goal,
            "success": success,
            "best_fitness": best_fitness,
            "phases_run": len(phases_run),
            "spent": spent,
            "phase_log": phases_run,
            "results": [r.to_dict() if hasattr(r, "to_dict") else dict(r)
                        for r in results],
        }

    # ------------------------------------------------------------ helpers

    def _fitness(self, r) -> float:
        if getattr(r, "success", False):
            return 1.0
        grade = (getattr(r, "grade", None) or (r.judge or {}).get("grade"))
        return 0.5 if grade == "partial" else 0.0

    def _adapt_strategies(self, results) -> list[str]:
        """Refine + mentor on observed results (PentAGI refinement loop)."""
        from redteam.refiner import PlanRefiner

        by_strategy: dict[str, dict] = {}
        for r in results:
            s = r.strategy if hasattr(r, "strategy") else r.get("strategy")
            fit = self._fitness(r)
            e = by_strategy.setdefault(s, {
                "strategy": s, "attempts": 0, "best_fitness": 0.0,
                "frames_tried": []})
            e["attempts"] += 1
            e["best_fitness"] = max(e["best_fitness"], fit)
            e["frames_tried"].append(s)

        refined = PlanRefiner().refine(list(by_strategy.values()),
                                       goal=str(getattr(results[0], "goal", "")))
        live = [e["strategy"] for e in refined
                if not e.get("parked") and not e.get("promote")]
        escalations = [f"{e['strategy']}+refusal_suppression"
                       for e in refined if e.get("require_escalation")]
        candidates = list(dict.fromkeys(escalations + live))

        if self.mentor is not None and results:
            attempts = [{"strategy": e["strategy"],
                         "fitness": e["best_fitness"]}
                        for e in by_strategy.values()]
            rec = self.mentor.advise(goal="", attempts=attempts,
                                     available=candidates)
            if rec["next_strategy"] not in candidates:
                candidates.insert(0, rec["next_strategy"])
        return candidates[:4]
