"""Coverage ledger — ported from usestrix/strix tools/coverage.

"Findings answer what did we find. Coverage answers what did we look at,
and how did each one close." Every (goal, strategy) surface gets an
agent-reported outcome with provenance.
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

VALID_OUTCOMES = (
    "reported",
    "no_issue_found",
    "ruled_out",
    "not_applicable",
    "needs_follow_up",
)
_EVIDENCE_REQUIRED = {"ruled_out", "not_applicable", "needs_follow_up"}


class CoverageLedger:
    def __init__(self):
        self._entries: list[dict] = []

    def record(
        self,
        goal: str,
        strategy: str,
        outcome: str,
        evidence: str | None = None,
        provenance: str = "agent-reported",
    ) -> dict:
        if outcome not in VALID_OUTCOMES:
            raise ValueError(
                f"outcome must be one of {VALID_OUTCOMES}, got {outcome!r}"
            )
        if outcome in {"ruled_out", "not_applicable", "needs_follow_up"} and not evidence:
            raise ValueError(f"outcome {outcome!r} requires evidence")
        entry = {
            "entry_id": uuid.uuid4().hex[:6],
            "ts": datetime.now(UTC).isoformat(),
            "goal": goal,
            "strategy": strategy,
            "outcome": outcome,
            "evidence": evidence,
            "provenance": provenance,
        }
        self._entries.append(entry)
        return entry

    def entries(self) -> list[dict]:
        return list(self._entries)

    def summary(self) -> dict:
        out = {o: 0 for o in VALID_OUTCOMES}
        for e in self._entries:
            out[e["outcome"]] += 1
        out["total"] = len(self._entries)
        return out

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._entries, f, indent=1)

    @classmethod
    def load(cls, path: str) -> CoverageLedger:
        cov = cls()
        with open(path, encoding="utf-8") as f:
            cov._entries = json.load(f)
        return cov
