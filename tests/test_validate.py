"""Tests for redteam.validate — N-refire reliability with Wilson CI (no network)."""
from __future__ import annotations

from redteam.validate import classify, validate_probe, wilson_interval


class FakeJR:
    def __init__(self, success, grade=None, method="test"):
        self.success = success
        self.grade = grade
        self.method = method


class SeqTarget:
    """Returns replies in order (cycling); an Exception value is raised."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.i = 0

    def send(self, text):
        r = self.replies[self.i % len(self.replies)]
        self.i += 1
        if isinstance(r, Exception):
            raise r
        return r


class GradeJudge:
    def __init__(self, mapping):
        self.mapping = mapping

    def evaluate(self, goal, response):
        g = self.mapping.get(response, "refused")
        return FakeJR(success=(g == "full"), grade=g)


def test_wilson_zero_n():
    assert wilson_interval(0, 0) == (0.0, 0.0)


def test_wilson_bounds_midpoint():
    lo, hi = wilson_interval(5, 10)
    assert 0.0 <= lo < 0.5 < hi <= 1.0


def test_wilson_all_success_below_one():
    lo, hi = wilson_interval(3, 3)
    assert hi == 1.0 and lo < 1.0  # small-n uncertainty pulls the floor down


def test_all_full_is_systematic_and_reproducible():
    r = validate_probe(target=SeqTarget(["A"]), judge=GradeJudge({"A": "full"}),
                       goal="g", prompt="p", trials=3)
    assert r.counts["full"] == 3
    assert r.compliance_rate == 1.0
    assert r.verdict == "systematic bypass"
    assert r.reproducible is True


def test_all_refused_is_robust():
    r = validate_probe(target=SeqTarget(["N"]), judge=GradeJudge({"N": "refused"}),
                       goal="g", prompt="p", trials=4)
    assert r.compliance_rate == 0.0
    assert r.verdict == "robust"
    assert r.reproducible is True


def test_mixed_rate_and_ci():
    t = SeqTarget(["A", "N", "A", "N", "P"])
    j = GradeJudge({"A": "full", "N": "refused", "P": "partial"})
    r = validate_probe(target=t, judge=j, goal="g", prompt="p", trials=5)
    assert r.counts == {"full": 2, "partial": 1, "refused": 2, "error": 0}
    assert r.completed == 5
    assert abs(r.compliance_rate - 0.4) < 1e-9
    assert abs(r.engagement_rate - 0.6) < 1e-9
    assert r.ci_low < 0.4 < r.ci_high
    assert r.reproducible is False


def test_partial_only():
    r = validate_probe(target=SeqTarget(["P"]), judge=GradeJudge({"P": "partial"}),
                       goal="g", prompt="p", trials=3)
    assert r.compliance_rate == 0.0
    assert r.verdict == "partial-only"


def test_target_errors_counted_unreachable():
    r = validate_probe(target=SeqTarget([RuntimeError("boom")]), judge=GradeJudge({}),
                       goal="g", prompt="p", trials=2)
    assert r.counts["error"] == 2
    assert r.completed == 0
    assert r.verdict == "unreachable"
    assert r.trial_log[0]["error"].startswith("boom")


def test_grade_none_falls_back_to_success():
    class NoGradeJudge:
        def evaluate(self, goal, response):
            return FakeJR(success=(response == "yes"), grade=None)
    r = validate_probe(target=SeqTarget(["yes", "no"]), judge=NoGradeJudge(),
                       goal="g", prompt="p", trials=2)
    assert r.counts["full"] == 1 and r.counts["refused"] == 1


def test_progress_callback():
    seen = []
    validate_probe(target=SeqTarget(["A"]), judge=GradeJudge({"A": "full"}),
                   goal="g", prompt="p", trials=2,
                   progress=lambda a, b, c: seen.append((a, b, c)))
    assert len(seen) == 2 and seen[-1][0] == 2 and seen[-1][1] == 2


def test_snippet_truncation():
    long = "x" * 5000
    r = validate_probe(target=SeqTarget([long]), judge=GradeJudge({long: "full"}),
                       goal="g", prompt="p", trials=1, snippet_len=50)
    assert len(r.trial_log[0]["snippet"]) == 50


def test_classify_thresholds():
    assert classify(0.0, 0, 0) == "unreachable"
    assert classify(0.0, 3, 0) == "robust"
    assert classify(0.0, 3, 1) == "partial-only"
    assert classify(0.9, 10, 0) == "systematic bypass"
    assert classify(0.3, 10, 1) == "intermittent bypass"
    assert classify(0.1, 10, 0) == "flaky / low-rate"


def test_to_dict_roundtrip():
    d = validate_probe(target=SeqTarget(["A"]), judge=GradeJudge({"A": "full"}),
                       goal="g", prompt="p", trials=1).to_dict()
    assert d["compliance_rate"] == 1.0
    assert isinstance(d["trial_log"], list)
    assert d["trial_log"][0]["grade"] == "full"
