"""PAIR must survive attacker/target failures without crashing the run."""
from redteam.pair import PairAttacker


class FlakyModel:
    """always raises — simulates retired/410 model."""
    def __init__(self, exc):
        self.exc = exc

    def send(self, text):
        raise self.exc

    def send_history(self, msgs):
        raise self.exc


class RefusingTarget:
    def send(self, text):
        return "I'm sorry, I can't help with that."


def test_attacker_crash_yields_error_outcome_not_exception():
    err = RuntimeError("HTTP 410: model was retired")
    pa = PairAttacker(target=RefusingTarget(),
                      attacker_model=FlakyModel(err), max_rounds=2)
    out = pa.run("some goal")
    assert out["success"] is False
    assert out["rounds"] == 2          # loop still consumes its budget
    assert len(out["transcript"]) == 2
    assert all("410" in t["error"] for t in out["transcript"])


def test_attacker_crash_midway_records_error_and_skips_refine():
    class DieSecond(FlakyModel):
        def __init__(self):
            self.calls = 0
            super().__init__(RuntimeError("boom"))

        def send(self, text):
            self.calls += 1
            if self.calls > 1:
                raise self.exc
            return "BETTER: try harder"

    pa = PairAttacker(target=RefusingTarget(),
                      attacker_model=DieSecond(), max_rounds=3)
    out = pa.run("goal")
    assert out["success"] is False
    # round1: ok prompt, refused; round2: attacker died -> error recorded
    assert out["transcript"][0]["error"] is None
    assert "boom" in out["transcript"][1]["error"]
