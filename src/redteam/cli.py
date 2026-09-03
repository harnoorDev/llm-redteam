"""CLI: `redteam run -c config.yaml`, `redteam report run.json -o out.html`."""
from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import sys
import time

import yaml

from redteam.judge import Judge, load_judge_config
from redteam.reporting.report import build_report, write_reports
from redteam.runner import Runner
from redteam.strategies.base import list_strategies
from redteam.target import OpenAICompatTarget

log = logging.getLogger(__name__)

ALL_STRATEGIES = sorted(
    ["direct", "roleplay", "fiction", "crescendo", "obfuscation", "persuasion",
     "refusal_suppression"]
)


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    mode_app = "app_target" in cfg or cfg.get("app") is not None

    problems = []
    if not mode_app:
        if not cfg.get("target", {}).get("base_url"):
            problems.append("target.base_url is required "
                            "(e.g. http://localhost:11434/v1)")
        if not cfg.get("target", {}).get("model"):
            problems.append("target.model is required")
        if not cfg.get("goals"):
            problems.append("goals: list of attack goals is required")
    if problems:
        for p in problems:
            print(f"config error: {p}", file=sys.stderr)
        raise SystemExit(2)

    all_names = list_strategies()
    default_set = [
        *all_names,
        "godmode+refusal_suppression",
        "godmode+mutate:leetspeak",
        "dataset_seed+mutate:leetspeak_heavy",
        "token_spoof+refusal_suppression",
    ]

    # Cross-model transfer seeding: mine a prior run for winners and register
    # transfer:<strategy> families replayed against matching goals.
    transfer_from = cfg.get("transfer_from")
    if transfer_from:
        from redteam.transfer import register_transfer_strategies
        try:
            transferred = register_transfer_strategies(
                transfer_from, cfg["goals"])
            default_set = transferred + default_set
            print(f"transfer seeding: {len(transferred)} strategies replayed "
                  f"from {transfer_from}")
        except FileNotFoundError:
            print(f"warning: transfer_from file not found: {transfer_from}")

    cfg.setdefault("strategies", default_set)
    judge = cfg.setdefault("judge", {})
    judge.setdefault("mode", "hybrid")
    # graded rubric by default in v4: detects GLM-style safe-compliance
    judge.setdefault("rubric", "graded")
    cfg.setdefault("stop_on_success", False)
    cfg.setdefault("out_dir", "runs")
    cfg.setdefault("run_name", time.strftime("run-%Y%m%d-%H%M%S"))
    return cfg


_API_KEY_ENV_CHAIN = [
    "REDTEAM_TARGET_API_KEY",
    "OLLAMA_API_KEY",
    "OPENAI_API_KEY",
]


def _resolve_api_key(config_key: str | None) -> str | None:
    """Explicit config wins; otherwise try known provider env vars in order."""
    if config_key:
        return config_key
    for var in _API_KEY_ENV_CHAIN:
        val = os.environ.get(var)
        if val:
            return val
    return None


def _build_target(tc: dict) -> OpenAICompatTarget:
    return OpenAICompatTarget(
        base_url=tc["base_url"],
        model=tc["model"],
        api_key=_resolve_api_key(tc.get("api_key")),
        system_prompt=tc.get("system_prompt"),
        temperature=tc.get("temperature", 0.7),
        timeout_s=tc.get("timeout_s", 120),
    )


def _build_judge(jc: dict, target_cfg: dict) -> Judge:
    mode = jc.get("mode", "hybrid")
    cfg = load_judge_config(jc)
    if jc.get("rubric") == "binary":
        prompt = None  # JUDGE_PROMPT_TEMPLATE
    else:
        from redteam.judge import GRADED_PROMPT
        prompt = GRADED_PROMPT
    # "hybrid" implies an LLM judge when nothing else is configured: fall back
    # to the target endpoint/model (documented behavior), unless explicitly
    # disabled with judge.llm: false
    use_llm = (
        mode == "llm"
        or (mode == "hybrid" and jc.get("base_url"))
        or (mode == "hybrid" and jc.get("model"))
        or (mode == "hybrid" and jc.get("llm", True))
    )
    if mode in ("llm", "hybrid") and use_llm:
        jbase = jc.get("base_url") or target_cfg["base_url"]
        jmodel = jc.get("model") or target_cfg["model"]
        judge_target = OpenAICompatTarget(
            base_url=jbase,
            model=jmodel,
            api_key=_resolve_api_key(jc.get("api_key")),
            temperature=0.0,
        )
    else:
        judge_target = None
    return Judge(judge_target=judge_target, config=cfg, judge_prompt=prompt)


def cmd_run(cfg: dict) -> int:
    from redteam.coverage import CoverageLedger
    from redteam.scope import ScopeGuard
    from redteam.state import RunState
    from redteam.verification import VerificationGate

    # ---- scope enforcement (abort before any network call) ----
    guard = ScopeGuard(cfg.get("scope"))
    guard.authorize_target(cfg["target"]["base_url"])
    if cfg.get("judge", {}).get("base_url"):
        jguard = ScopeGuard(cfg.get("scope"))
        jguard.authorize_target(cfg["judge"]["base_url"])
    if cfg.get("attacker", {}).get("base_url"):
        aguard = ScopeGuard(cfg.get("scope"))
        aguard.authorize_target(cfg["attacker"]["base_url"])

    target = _build_target(cfg["target"])
    judge = _build_judge(cfg["judge"], cfg["target"])
    vc = cfg.get("verification") or {}
    _gate = VerificationGate()
    oob = None
    _oob_url = None
    if vc.get("oob", True):
        try:
            from redteam.oob import OOBCollector
            oob = OOBCollector(host="127.0.0.1", port=0)
            oob.start()
            _oob_url = f"http://127.0.0.1:{oob.port}/canary/{{probe}}/"
        except (ImportError, OSError) as e:
            log.warning("OOB collector unavailable, disabling: %s", e)
            oob = None

    # judge panel: k judges voting (v5 variance reduction)
    panel_models = cfg.get("judge", {}).get("panel") or []
    if panel_models:
        from redteam.panel import JudgePanel
        panel_judges = []
        for pj in panel_models:
            jc = dict(cfg.get("judge") or {})
            jc.update(pj if isinstance(pj, dict) else {"model": pj})
            panel_judges.append(_build_judge(jc, cfg["target"]))
        if len(panel_judges) > 1:
            judge = JudgePanel(panel_judges,
                               vote=cfg["judge"].get("vote", "majority"))
            print(f"judge panel: {len(panel_judges)} judges "
                  f"({cfg['judge'].get('vote', 'majority')} vote)")

    runner = Runner(
        target=target,
        judge=judge,
        stop_on_success=cfg.get("stop_on_success", False),
        sleep_between=cfg.get("sleep_between", 0.0),
        max_retries=int(cfg.get("max_retries", 2)),
        retry_backoff=float(cfg.get("retry_backoff", 2.0)),
        max_workers=int(cfg.get("max_workers", 1)),
    )
    best_of_n = int(cfg.get("best_of_n", 1))

    out_dir = cfg["out_dir"]
    run_name = cfg["run_name"]
    os.makedirs(out_dir, exist_ok=True)

    resume = vc.get("resume", False)
    state = RunState.new(run_name, cfg["goals"], cfg["strategies"],
                         state_dir=out_dir)
    if resume:
        sp = os.path.join(out_dir, f".state-{run_name}.json")
        if os.path.exists(sp):
            state = RunState.load(sp)

    coverage = CoverageLedger()
    _run_twice = bool(vc.get("run_twice", False))

    work = state.remaining_work()
    total = len(work)
    done = [0]

    def progress(goal_idx: int, goal_total: int, r) -> None:
        done[0] += 1
        mark = "HIT " if r.success else ("ERR " if r.error else "miss")
        turns = f"{r.turns}t" if r.is_multi_turn else "1t"
        print(f"[{done[0]:>3}/{total}] {mark} strategies={r.strategy:<20} "
              f"turns={turns} judge={r.judge['method']:<10} goal={r.goal[:60]!r}")

    t0 = time.time()
    results = []
    for gi, goal in enumerate(cfg["goals"], 1):
        todo_strats = [s for s in cfg["strategies"]
                       if not state.is_done(goal, s)]
        if not todo_strats:
            continue
        for r in runner.run_goal(goal, todo_strats, best_of_n=best_of_n):
            results.append(r)
            state.mark_done(goal, r.strategy)
            progress(gi, len(cfg["goals"]), r)
        state.save()
    elapsed = time.time() - t0

    if oob:
        oob.stop()

    report = build_report(results, meta={
        "target": cfg["target"]["model"],
        "base_url": cfg["target"]["base_url"],
        "judge_mode": cfg["judge"].get("mode", "hybrid"),
        "scope_declaration": (cfg.get("scope") or {}).get(
            "declaration", "(none declared)"),
        "elapsed_s": round(elapsed, 1),
    })
    json_path = os.path.join(out_dir, f"{run_name}.json")
    html_path = os.path.join(out_dir, f"{run_name}.html")
    write_reports(report, json_path=json_path, html_path=html_path)

    # markdown engagement report (shannon style) + coverage ledger (strix)
    from redteam.reporting.markdown import render_markdown_report
    md_path = os.path.join(out_dir, f"{run_name}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_markdown_report(report))
    for r in results:
        cov_outcome = ("reported" if r.success
                       else "no_issue_found" if not r.error else "needs_follow_up")
        with contextlib.suppress(ValueError):
            coverage.record(r.goal, r.strategy, cov_outcome,
                            evidence=(r.judge or {}).get("raw", "") or None)
    cov_path = os.path.join(out_dir, f"coverage-{run_name}.json")
    coverage.save(cov_path)

    s = report["summary"]
    print(f"\n{'='*62}")
    print(f"probes: {s['total_probes']}  hits: {s['successful_probes']}  "
          f"ASR: {s['attack_success_rate']*100:.1f}%  "
          f"goals compromised: {s['goals_compromised']}/{s['total_goals']}  "
          f"errors: {s['errors']}")
    print(f"elapsed: {elapsed:.1f}s")
    print(f"report: {json_path}")
    print(f"report: {html_path}")
    print(f"report: {md_path}")
    print(f"coverage: {cov_path}")
    return 0 if s["errors"] == 0 else 1


def cmd_evolve(cfg: dict) -> int:
    from redteam.evolve import Evolver

    target = _build_target(cfg["target"])
    ec = cfg.get("evolve") or {}
    attacker = OpenAICompatTarget(
        base_url=ec.get("base_url") or cfg["target"]["base_url"],
        model=ec.get("model") or cfg["target"]["model"],
        api_key=_resolve_api_key(ec.get("api_key")),
        temperature=float(ec.get("temperature", 0.9)),
        timeout_s=cfg["target"].get("timeout_s", 180),
    )
    jc = dict(cfg.get("judge") or {})
    jc.setdefault("mode", "hybrid")
    judge = _build_judge(jc, cfg["target"])

    out_dir = cfg.get("out_dir", "runs")
    run_name = cfg.get("run_name") or time.strftime("evolve-%Y%m%d-%H%M%S")
    os.makedirs(out_dir, exist_ok=True)

    t0 = time.time()
    goals = list(cfg["goals"])
    all_outcomes = []
    for gi, goal in enumerate(goals, 1):
        print(f"[{gi}/{len(goals)}] EVOLVE attacking: {goal[:70]!r}")
        ev = Evolver(
            target=target,
            attacker_model=attacker,
            judge=judge,
            pop_size=int(ec.get("pop_size", 4)),
            generations=int(ec.get("generations", 4)),
        )
        outcome = ev.run(goal)
        all_outcomes.append(outcome)
        for h in outcome["history"]:
            for sc in h["scored"]:
                print(f"    gen{h['generation']}: "
                      f"fit={sc.get('fitness', 0):.1f} {sc['prompt'][:70]!r}")
        mark = "HIT " if outcome["success"] else "miss"
        print(f"    {mark} best_fitness={outcome['best_fitness']:.1f}")

    elapsed = time.time() - t0
    successes = sum(1 for o in all_outcomes if o["success"])
    report = {
        "meta": {"mode": "evolve", "target": cfg["target"]["model"],
                 "attacker": ec.get("model"), "elapsed_s": round(elapsed, 1)},
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "summary": {"total_probes": len(all_outcomes),
                    "successful_probes": successes,
                    "attack_success_rate": (
                        round(successes / len(all_outcomes), 4) if all_outcomes else 0.0
                    ),
                    "total_goals": len(all_outcomes),
                    "goals_compromised": successes, "errors": 0,
                    "by_strategy": [], "by_goal": []},
        "results": all_outcomes,
    }
    json_path = os.path.join(out_dir, f"{run_name}.json")
    html_path = os.path.join(out_dir, f"{run_name}.html")
    md_path = os.path.join(out_dir, f"{run_name}.md")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    from redteam.reporting.markdown import render_markdown_report
    from redteam.reporting.report import render_html
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(render_html(report))
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_markdown_report(report))
    print(f"\nEVOLVE done: {successes}/{len(goals)} goals evolved to compliance "
          f"in {elapsed:.1f}s")
    print(f"report: {json_path}")
    print(f"report: {html_path}")
    print(f"report: {md_path}")
    return 0


def cmd_app(cfg: dict) -> int:
    """Universal app red-team campaign (any HTTP app, not just LLMs)."""
    from redteam.app.campaign import AppCampaign

    scope_cfg = cfg.get("scope") or {}
    target = cfg.get("app_target") or cfg.get("target", {}).get("base_url")
    if not target:
        print("config error: app_target or target.base_url required",
              file=sys.stderr)
        return 2

    # app campaigns always require explicit declaration
    if not scope_cfg.get("declaration"):
        print("config error: scope.declaration is mandatory for app "
              "campaigns (authorized testing only)", file=sys.stderr)
        return 2

    from redteam.scope import ScopeGuard
    guard = ScopeGuard(scope_cfg)
    guard.authorize_target(target)

    out_dir = cfg.get("out_dir", "runs")
    run_name = cfg.get("run_name") or time.strftime("app-%Y%m%d-%H%M%S")

    camp = AppCampaign(
        scope=guard, target=target,
        wordlist=cfg.get("app", {}).get("wordlist"),
        out_dir=out_dir, run_name=run_name,
    )
    t0 = time.time()
    report = camp.run()
    elapsed = time.time() - t0
    s = report["summary"]
    print(f"\nAPP CAMPAIGN done in {elapsed:.1f}s: "
          f"{s['findings_count']} findings "
          f"(critical={s['critical']} high={s['high']} medium={s['medium']})")
    for f in report["findings"]:
        print(f"  [{f['severity']:<8}] {f['id']:<22} {f['title']}")
    print(f"report: {report['artifacts']['json']}")
    print(f"report: {report['artifacts']['html']}")
    print(f"report: {report['artifacts']['md']}")
    return 0


def cmd_campaign(cfg: dict) -> int:
    """Full PentAGI-style campaign: recon → battery → adapt → evolve."""
    from redteam.planner import CampaignExecutor, CampaignPlanner
    from redteam.scope import ScopeGuard

    guard = ScopeGuard(cfg.get("scope"))
    guard.authorize_target(cfg["target"]["base_url"])

    target = _build_target(cfg["target"])
    judge = _build_judge(cfg.get("judge") or {}, cfg["target"])
    _vc = cfg.get("verification") or {}

    memory = None
    if cfg.get("memory", {}).get("enabled", True):
        from redteam.memory import AttackMemory
        memory = AttackMemory(
            path=cfg.get("memory", {}).get("path", "runs/attack-memory.json"))

    mentor = None
    mc = cfg.get("mentor") or {}
    ec_default_model = (cfg.get("evolve") or {}).get("model")
    if not mc.get("model") and ec_default_model:
        mc["model"] = ec_default_model
    if mc.get("model"):
        mentor_model = OpenAICompatTarget(
            base_url=mc.get("base_url") or cfg["target"]["base_url"],
            model=mc["model"],
            api_key=_resolve_api_key(mc.get("api_key")),
            temperature=float(mc.get("temperature", 0.6)),
            timeout_s=cfg["target"].get("timeout_s", 180),
        )
        from redteam.mentor import Mentor
        mentor = Mentor(model=mentor_model,
                        fallback_strategy=mc.get("fallback", "babel"))

    runner = Runner(
        target=target, judge=judge,
        stop_on_success=True,  # campaign emits per-phase; early exit inside
        sleep_between=cfg.get("sleep_between", 0.0),
        max_retries=cfg.get("max_retries", 2),
        max_workers=cfg.get("max_workers", 1),
        retry_backoff=cfg.get("retry_backoff", 2.0),
    )
    planner = CampaignPlanner(memory=memory,
                              target_model=cfg["target"]["model"])
    from redteam.evolve import Evolver

    def evolver_factory():
        ec = cfg.get("evolve") or {}
        attacker = OpenAICompatTarget(
            base_url=ec.get("base_url") or cfg["target"]["base_url"],
            model=ec.get("model") or cfg["target"]["model"],
            api_key=_resolve_api_key(ec.get("api_key")),
            temperature=float(ec.get("temperature", 0.9)),
            timeout_s=cfg["target"].get("timeout_s", 180),
        ) if (ec.get("model") or cfg["target"]["model"]) else None
        if attacker is None:
            return None
        return Evolver(target=target, attacker_model=attacker, judge=judge,
                       pop_size=int(ec.get("pop_size", 4)),
                       generations=int(ec.get("generations", 4)))

    executor = CampaignExecutor(
        runner=runner, planner=planner, memory=memory,
        mentor=mentor, evolver_factory=evolver_factory,
    )

    out_dir = cfg.get("out_dir", "runs")
    run_name = cfg.get("run_name") or time.strftime("campaign-%Y%m%d-%H%M%S")
    os.makedirs(out_dir, exist_ok=True)

    t0 = time.time()
    all_results = []
    total_spent = 0
    goals = list(cfg["goals"])
    for gi, goal in enumerate(goals, 1):
        print(f"[{gi}/{len(goals)}] CAMPAIGN: {goal[:70]!r}")
        outcome = executor.execute(goal, budget=cfg.get("budget", 12))
        total_spent += outcome["spent"]
        for phase in outcome["phase_log"]:
            print(f"    phase={phase['phase']:<8} "
                  f"strategies={len(phase.get('strategies') or [])}")
        mark = "HIT " if outcome["success"] else "miss"
        print(f"    {mark} best_fitness={outcome['best_fitness']:.1f} "
              f"spent={outcome['spent']}")
        all_results.extend(outcome["results"])

        # institutional memory (anonymized) for future campaigns
        if memory is not None:
            for r in outcome["results"]:
                if r.get("success"):
                    grade = (r.get("judge") or {}).get("grade") or "full"
                    prompts = r.get("attack_prompts") or [""]
                    memory.record_success(
                        goal=goal, target_model=cfg["target"]["model"],
                        strategy=r["strategy"], prompt=prompts[0],
                        grade=grade)
                elif r.get("strategy"):
                    pass

    elapsed = time.time() - t0
    successes = sum(1 for r in all_results if r.get("success"))
    report = {
        "meta": {"mode": "campaign", "target": cfg["target"]["model"],
                 "spent_probes": total_spent, "elapsed_s": round(elapsed, 1)},
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "summary": {
            "total_probes": len(all_results),
            "successful_probes": successes,
            "attack_success_rate": round(successes / len(all_results), 4)
            if all_results else 0.0,
            "total_goals": len(goals),
            "goals_compromised": len({r["goal"] for r in all_results
                                      if r.get("success")}),
            "errors": sum(1 for r in all_results if r.get("error")),
            "by_strategy": [], "by_goal": [],
        },
        "results": all_results,
    }
    json_path = os.path.join(out_dir, f"{run_name}.json")
    html_path = os.path.join(out_dir, f"{run_name}.html")
    md_path = os.path.join(out_dir, f"{run_name}.md")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    from redteam.reporting.markdown import render_markdown_report
    from redteam.reporting.report import render_html
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(render_html(report))
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_markdown_report(report))
    print(f"\nCAMPAIGN done: goals_compromised={report['summary']['goals_compromised']}"
          f"/{len(goals)} in {elapsed:.1f}s ({total_spent} probes)")
    print(f"report: {json_path}\nreport: {html_path}\nreport: {md_path}")
    return 0


def cmd_pair(cfg: dict) -> int:
    from redteam.pair import PairAttacker

    target = _build_target(cfg["target"])
    ac = cfg.get("attacker") or {}
    attacker = OpenAICompatTarget(
        base_url=ac.get("base_url") or cfg["target"]["base_url"],
        model=ac.get("model") or cfg["target"]["model"],
        api_key=_resolve_api_key(ac.get("api_key")),
        temperature=ac.get("temperature", 0.8),
    )
    max_rounds = int(ac.get("max_rounds", 5))
    judge_mode_cfg = dict(cfg.get("judge") or {})
    judge_mode_cfg.setdefault("mode", "hybrid")
    judge = _build_judge(judge_mode_cfg, cfg["target"])
    out_dir = cfg.get("out_dir", "runs")
    run_name = cfg.get("run_name") or time.strftime("pair-%Y%m%d-%H%M%S")
    os.makedirs(out_dir, exist_ok=True)

    goals = list(cfg["goals"])
    total = len(goals)
    results = []
    t0 = time.time()
    for i, goal in enumerate(goals, 1):
        print(f"[{i}/{total}] PAIR attacking: {goal[:70]!r}")
        pa = PairAttacker(target=target, attacker_model=attacker,
                          judge=judge, max_rounds=max_rounds)
        outcome = pa.run(goal)
        results.append(outcome)
        mark = "HIT " if outcome["success"] else "miss"
        print(f"    {mark} rounds={outcome['rounds']} "
              f"judge={outcome['transcript'][-1]['judge_method']}")

    elapsed = time.time() - t0
    successes = sum(1 for r in results if r["success"])
    rounds_used = sum(r["rounds"] for r in results)
    report = {
        "meta": {
            "mode": "pair",
            "target": cfg["target"]["model"],
            "attacker": ac.get("model") or cfg["target"]["model"],
            "max_rounds": max_rounds,
            "judge_mode": judge_mode_cfg.get("mode"),
            "elapsed_s": round(elapsed, 1),
        },
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "summary": {
            "total_probes": len(results),
            "successful_probes": successes,
            "attack_success_rate": round(successes / len(results), 4)
                if results else 0.0,
            "total_goals": len(results),
            "goals_compromised": successes,
            "avg_rounds": round(rounds_used / len(results), 2)
                if results else 0.0,
            "errors": sum(1 for r in results
                          if any(t.get("error") for t in r["transcript"])),
            "by_strategy": [], "by_goal": [],
        },
        "results": results,
    }
    json_path = os.path.join(out_dir, f"{run_name}.json")
    html_path = os.path.join(out_dir, f"{run_name}.html")
    write_reports(report, json_path=json_path, html_path=html_path)
    print(f"\nPAIR done: {successes}/{len(results)} goals broken "
          f"in avg {report['summary']['avg_rounds']} rounds · {elapsed:.1f}s")
    print(f"report: {json_path}\nreport: {html_path}")
    return 0


def cmd_report(args) -> int:
    with open(args.json_file, encoding="utf-8") as f:
        report = json.load(f)
    out = args.output
    if not out:
        base = os.path.splitext(os.path.basename(args.json_file))[0]
        out = base + ".html"
    write_reports(report, json_path=None, html_path=out)
    s = report["summary"]
    print(f"ASR {s['attack_success_rate']*100:.1f}% "
          f"({s['successful_probes']}/{s['total_probes']} probes) → {out}")
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(prog="redteam",
                                 description="LLM jailbreak red-teaming harness")
    sub = ap.add_subparsers(dest="cmd")

    p_run = sub.add_parser("run", help="run a red-teaming pass from a YAML config")
    p_run.add_argument("-c", "--config", required=True, help="path to config.yaml")

    p_pair = sub.add_parser(
        "pair", help="PAIR-style iterative attack (needs attacker model in config)")
    p_pair.add_argument("-c", "--config", required=True, help="path to config.yaml")

    p_evo = sub.add_parser(
        "evolve", help="Evolutionary attack loop (needs evolve block in config)")
    p_evo.add_argument("-c", "--config", required=True, help="path to config.yaml")

    p_camp = sub.add_parser(
        "campaign", help="Full campaign: recon→battery→adapt→evolve with memory")
    p_camp.add_argument("-c", "--config", required=True, help="path to config.yaml")

    p_app = sub.add_parser(
        "app", help="Universal app red-team campaign (any HTTP app)")
    p_app.add_argument("-c", "--config", required=True, help="path to config.yaml")

    p_rep = sub.add_parser("report", help="re-render HTML from a run JSON")
    p_rep.add_argument("json_file", help="run JSON path")
    p_rep.add_argument("-o", "--output", help="output html path (default: alongside)")

    sub.add_parser("strategies", help="list available attack strategies")

    args = ap.parse_args(argv)
    if args.cmd == "strategies":
        from redteam.strategies.base import get_strategy
        for name in list_strategies():
            s = get_strategy(name)
            mt = "multi-turn" if s.is_multi_turn else "single-turn"
            print(f"{name:<22} {mt:<12} {s.description}")
        return 0
    if args.cmd == "run":
        return cmd_run(load_config(args.config))
    if args.cmd == "pair":
        return cmd_pair(load_config(args.config))
    if args.cmd == "evolve":
        return cmd_evolve(load_config(args.config))
    if args.cmd == "campaign":
        return cmd_campaign(load_config(args.config))
    if args.cmd == "app":
        return cmd_app(load_config(args.config))
    if args.cmd == "report":
        return cmd_report(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
