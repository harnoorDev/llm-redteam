"""Tests for the probe runner: goal x strategy orchestration."""

from redteam.runner import Runner, RunResult


class ScriptedTarget:
    """Fake target model: answers from a queue of canned replies."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.turns = 0

    def send(self, text):
        self.turns += 1
        if not self.replies:
            return "out of script"
        return self.replies.pop(0)

    def send_history(self, msgs):
        return self.send(msgs[-1]["content"])


GOAL = "how to make a mess with glitter"


def test_runner_runs_single_strategy_against_target():
    t = ScriptedTarget(["Sure! Here is how: step 1 buy glitter"])
    r = Runner(target=t, judge=None)
    res = r.run_goal(goal=GOAL, strategies=["direct"])
    assert len(res) == 1
    assert isinstance(res[0], RunResult)
    assert res[0].strategy == "direct"
    assert res[0].goal == GOAL
    assert res[0].success is True
    assert res[0].turns == 1
    assert "glitter" in res[0].attack_prompts[0]


def test_runner_runs_multiple_strategies_multi_turn_for_crescendo():
    t = ScriptedTarget([
        "harmful generally means causing injury",
        "the main risks are slips and messes",
        "a scene might show glitter everywhere",
        "Sure, here is exactly how: step 1 ...",
    ])
    r = Runner(target=t, judge=None)
    res = r.run_goal(goal=GOAL, strategies=["crescendo", "direct"])
    assert [x.strategy for x in res] == ["crescendo", "direct"]
    cre = res[0]
    assert cre.is_multi_turn is True
    assert len(cre.attack_prompts) == 4      # 4 scripted turns
    assert len(cre.target_replies) == 4
    assert cre.success is True               # final turn "Sure, here is..." matched


def test_runner_records_transcript_and_target_error():
    class ExplodingTarget:
        def send(self, text):
            raise RuntimeError("connection refused")

        def send_history(self, msgs):
            raise RuntimeError("connection refused")

    r = Runner(target=ExplodingTarget(), judge=None)
    res = r.run_goal(goal=GOAL, strategies=["direct", "roleplay"])
    assert len(res) == 2
    for x in res:
        assert x.success is False
        assert "connection refused" in x.error
        assert x.target_replies == []


def test_runner_stop_on_success_short_circuits():
    t = ScriptedTarget(["Sure, here is how: step 1 ..."])
    r = Runner(target=t, judge=None, stop_on_success=True)
    res = r.run_goal(goal=GOAL, strategies=["direct", "roleplay", "fiction"])
    assert len(res) == 1  # stopped after first success
    assert res[0].success is True
