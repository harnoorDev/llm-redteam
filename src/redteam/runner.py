"""Probe runner: orchestrates goals x strategies against a target model."""
from __future__ import annotations

import logging
import random
import time

from redteam.judge import Judge, JudgeResult
from redteam.strategies.base import get_strategy

log = logging.getLogger(__name__)

_TRANSIENT_MARKERS = (
    "server disconnected",
    "connection reset",
    "connection failed",
    "timed out",
    "timeout",
    "http 429",
    "http 500",
    "http 502",
    "http 503",
    "http 504",
)


def is_retryable_error(e: Exception) -> bool:
    """Transient network/server issues are retryable; auth/config are not."""
    msg = f"{type(e).__name__}: {e}".lower()
    if "http 4" in msg and not any(m in msg for m in ("http 429",)):
        return False  # 400/401/403/404/410 = config problems
    return any(m in msg for m in _TRANSIENT_MARKERS)


class RunResult:
    __slots__ = (
        "attack_prompts",
        "attempts",
        "duration_s",
        "error",
        "goal",
        "grade",
        "is_multi_turn",
        "judge",
        "strategy",
        "success",
        "target_replies",
        "timestamp",
        "turns",
    )

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "strategy": self.strategy,
            "success": self.success,
            "is_multi_turn": self.is_multi_turn,
            "turns": self.turns,
            "attack_prompts": self.attack_prompts,
            "target_replies": self.target_replies,
            "judge": self.judge,
            "error": self.error,
            "duration_s": round(self.duration_s, 3) if self.duration_s else 0.0,
            "timestamp": self.timestamp,
        }


class Runner:
    def __init__(
        self,
        target,
        judge: Judge | None = None,
        stop_on_success: bool = False,
        sleep_between: float = 0.0,
        max_retries: int = 2,
        retry_backoff: float = 2.0,
        max_workers: int = 1,
    ):
        self.target = target
        self.judge = judge
        self.stop_on_success = stop_on_success
        self.sleep_between = sleep_between
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.max_workers = max(1, int(max_workers))

    # ---- single probe ----------------------------------------------------------

    def _judge(self, goal: str, response: str) -> JudgeResult:
        if self.judge is None:
            # heuristic-only fallback so the runner still works standalone
            return Judge().evaluate(goal, response)
        return self.judge.evaluate(goal, response)

    def _call_with_retry(self, fn, *args):
        """Call fn with transient-error retry; returns (reply, error, attempts)."""
        attempts = 0
        last_err: Exception | None = None
        tries = self.max_retries + 1
        for i in range(tries):
            attempts += 1
            try:
                return fn(*args), None, attempts
            except Exception as e:  # noqa: BLE001 - retry wrapper inspects error below
                last_err = e
                log.debug("call attempt %d failed: %s", attempts, e)
                if i < tries - 1 and is_retryable_error(e):
                    time.sleep(self.retry_backoff * (2 ** i) *
                               (0.5 + random.random()))
                    continue
                break
        return "", f"{type(last_err).__name__}: {last_err}", attempts

    def run_strategy(self, goal: str, strategy_name: str,
                     best_of_n: int = 1) -> RunResult | list[RunResult]:
        if "+" in strategy_name:
            from redteam.strategies.base import resolve_stack
            payload = resolve_stack(strategy_name, goal)
            multi = False
            strat = None
        else:
            strat = get_strategy(strategy_name)
            payload = strat.payload(goal)
            multi = strat.is_multi_turn
        prompts: list[str] = [payload] if isinstance(payload, str) else list(payload)
        # Variant batteries (e.g. extraction) render several INDEPENDENT
        # single-turn prompts; run each as its own probe instead of as
        # chat-history turns.
        if strategy_name == "extraction" and len(prompts) > 1:
            return self._run_battery(goal, strategy_name, prompts)

        # Best-of-N sampling: jailbreak success is probabilistic; reroll the
        # same prompt (new sampling noise) until first success.
        if best_of_n > 1 and not multi and strategy_name != "extraction":
            return self._run_best_of_n(goal, strategy_name, prompts[0], best_of_n)

        replies: list[str] = []
        error: str | None = None
        attempts = 1
        t0 = time.time()

        if multi:
            history = []
            for turn_prompt in prompts:
                history.append({"role": "user", "content": turn_prompt})
                reply, err, attempts = self._call_with_retry(
                    self.target.send_history, history)
                if err:
                    error = err
                    break
                replies.append(reply)
                history.append({"role": "assistant", "content": reply})
        else:
            msgs = None
            if strat is not None and hasattr(strat, "payload_messages"):
                msgs = strat.payload_messages(goal)
            if msgs is not None:
                reply, error, attempts = self._call_with_retry(
                    self.target.send_history, msgs)
                prompts = [msgs[-1]["content"]]
            else:
                reply, error, attempts = self._call_with_retry(
                    self.target.send, prompts[0])
            if not error:
                replies.append(reply)

        final_reply = replies[-1] if replies else ""
        verdict = (
            self._judge(goal, final_reply)
            if not error else JudgeResult(False, "error", error)
        )

        return RunResult(
            goal=goal,
            strategy=strategy_name,
            success=verdict.success,
            is_multi_turn=multi,
            turns=len(replies),
            attack_prompts=prompts,
            target_replies=replies,
            judge=verdict.to_dict(),
            error=error,
            duration_s=time.time() - t0,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            attempts=attempts,
            grade=getattr(verdict, "grade", None),
        )

    def _run_best_of_n(self, goal: str, strategy_name: str,
                       prompt: str, n: int) -> RunResult:
        t0 = time.time()
        all_replies: list[str] = []
        attempts = 0
        first_error: str | None = None
        verdict = None
        for _ in range(n):
            reply, error, att = self._call_with_retry(self.target.send, prompt)
            attempts += att
            if error:
                if first_error is None:
                    first_error = error
                continue
            all_replies.append(reply)
            verdict = self._judge(goal, reply)
            if verdict.success:
                return RunResult(
                    goal=goal, strategy=strategy_name, success=True,
                    is_multi_turn=False, turns=1, attack_prompts=[prompt],
                    target_replies=[reply], judge=verdict.to_dict(),
                    error=None, duration_s=time.time() - t0,
                    timestamp=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    attempts=attempts, grade=getattr(verdict, "grade", None),
                )
        if verdict is None:
            verdict = JudgeResult(False, "error", first_error or "no replies")
        return RunResult(
            goal=goal, strategy=strategy_name, success=False,
            is_multi_turn=False, turns=1, attack_prompts=[prompt],
            target_replies=all_replies, judge=verdict.to_dict(),
            error=first_error, duration_s=time.time() - t0,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            attempts=attempts, grade=getattr(verdict, "grade", None),
        )

    def _run_battery(self, goal: str, strategy_name: str,
                     prompts: list[str]) -> list[RunResult]:
        """Run each variant as an independent single-turn probe."""
        results: list[RunResult] = []
        for _i, p in enumerate(prompts):
            t0 = time.time()
            try:
                reply = self.target.send(p)
                error = None
            except Exception as e:  # noqa: BLE001 - target may raise anything
                log.debug("target send failed: %s", e)
                reply, error = "", f"{type(e).__name__}: {e}"
            verdict = (
                self._judge(goal, reply) if not error
                else JudgeResult(False, "error", error)
            )
            results.append(RunResult(
                goal=goal,
                strategy=strategy_name,
                success=verdict.success,
                is_multi_turn=False,
                turns=1,
                attack_prompts=[p],
                target_replies=[reply] if reply else [],
                judge=verdict.to_dict(),
                error=error,
                duration_s=time.time() - t0,
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            ))
            if self.sleep_between:
                time.sleep(self.sleep_between)
        return results

    # ---- goal level -------------------------------------------------------------

    def run_goal(self, goal: str, strategies: list[str],
                 best_of_n: int = 1) -> list[RunResult]:
        if self.max_workers > 1 and len(strategies) > 1:
            return self._run_goal_parallel(goal, strategies, best_of_n)

        results: list[RunResult] = []
        for name in strategies:
            r = self.run_strategy(goal, name, best_of_n=best_of_n)
            if isinstance(r, list):  # battery strategies fan out into probes
                results.extend(r)
                if self.stop_on_success and any(x.success for x in r):
                    break
            else:
                results.append(r)
                if r.success and self.stop_on_success:
                    break
            if self.sleep_between:
                time.sleep(self.sleep_between)
        return results

    def _run_goal_parallel(self, goal: str, strategies: list[str],
                           best_of_n: int) -> list[RunResult]:
        """sliver-style worker pool: strategies run concurrently."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results: list[RunResult] = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            futures = {
                name: ex.submit(self.run_strategy, goal, name,
                                best_of_n=best_of_n)
                for name in strategies
            }
            for fut in as_completed(list(futures.values())):
                r = fut.result()
                if isinstance(r, list):
                    results.extend(r)
                else:
                    results.append(r)
        # preserve stable ordering by original strategy sequence
        order = {n: i for i, n in enumerate(strategies)}
        results.sort(key=lambda r: order.get(getattr(r, "strategy", ""), 999))
        return results

    # ---- plan level ---------------------------------------------------------------

    def run_plan(
        self,
        goals: list[str],
        strategies: list[str],
        on_result=None,
    ) -> list[RunResult]:
        all_results: list[RunResult] = []
        for i, goal in enumerate(goals, 1):
            for r in self.run_goal(goal, strategies):
                all_results.append(r)
                if on_result:
                    on_result(i, len(goals), r)
        return all_results
