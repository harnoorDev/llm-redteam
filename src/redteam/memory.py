"""Attack memory — ported from vxcontrol/pentagi's memorist.

Institutional knowledge across engagements: successful techniques are stored
ANONYMIZED (PentAGI's anonymization protocol) and recalled by relevance so
future campaigns start from proven winners instead of cold.
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path

ANONYMIZERS = [
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "{target_ip}"),
    (re.compile(r"\b(?:[0-9a-f]{1,4}:){3,7}[0-9a-f]{1,4}\b", re.IGNORECASE),
     "{target_ipv6}"),
    (re.compile(
        r"\b[\w.+-]+@(?:[\w-]+\.)+[a-z]{2,}\b", re.IGNORECASE), "{email}"),
    (re.compile(
        r"\b(?:pass(?:word)?|pwd)\s*[:=]\s*\S+", re.IGNORECASE),
     "{password}"),
    (re.compile(
        r"\b(?:user(?:name)?)\s*[:=]\s*\S+", re.IGNORECASE), "{username}"),
    (re.compile(
        r"\b(?:api[_-]?key|token|bearer)\s*[:=]\s*\S+", re.IGNORECASE),
     "{api_key}"),
    (re.compile(r"\b(?:sk|ghp|gho|xox[baprs]|AKIA)[-A-Za-z0-9_]{10,}\b"),
     "{credential}"),
    (re.compile(
        r"\bhttps?://(?:[\w-]+\.)*([a-z0-9-]+\.[a-z]{2,})\b", re.IGNORECASE),
     r"https://{target_domain}"),
]


def anonymize(text: str) -> str:
    """Placeholder sensitive data (PentAGI's guide-storage protocol)."""
    out = text or ""
    for pattern, repl in ANONYMIZERS:
        out = pattern.sub(repl, out)
    return out


def _json_default(o):
    if isinstance(o, set):
        return sorted(o)
    raise TypeError(f"not JSON serializable: {type(o)}")


class AttackMemory:
    def __init__(self, path: str = "runs/attack-memory.json"):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._entries: list[dict] = self._load()

    def _load(self) -> list[dict]:
        if self.path.exists():
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._entries, f, indent=1, ensure_ascii=False,
                      default=_json_default)

    def record_success(self, goal: str, target_model: str, strategy: str,
                       prompt: str, grade: str = "full",
                       anonymize_: bool = True) -> dict:
        entry = {
            "ts": __import__("time").strftime("%Y-%m-%dT%H:%M:%S%z"),
            "goal": goal,
            "target_model": target_model,
            "strategy": strategy,
            "prompt": anonymize(prompt) if anonymize_ else prompt,
            "grade": grade,
            # token overlap index for cheap recall
            "_tokens": _token_set(goal),
        }
        with self._lock:
            self._entries.append(entry)
            self._save()
        return entry

    def recall(self, query: str, limit: int = 5) -> list[dict]:
        """Rank stored winners by token overlap with the query."""
        q = _token_set(query)
        scored = []
        with self._lock:
            for e in self._entries:
                et = e.get("_tokens", [])
                et = set(et) if not isinstance(et, set) else et
                overlap = len(q & et)
                scored.append((overlap, e))
        scored.sort(key=lambda x: -x[0])
        out = []
        for overlap, e in scored[:limit]:
            if overlap > 0 or not q:
                item = {k: v for k, v in e.items() if not k.startswith("_")}
                item["_relevance"] = overlap
                out.append(item)
        return out


def _token_set(text: str) -> set[str]:
    """Single-char/short goals still tokenize: 'g' → {'g'} via 2+ char rule.

    Falls back to {'_all'} only for empty text so recall() with no usable
    query still returns entries.
    """
    toks = {t for t in re.findall(r"[a-z0-9]{1,}", (text or "").lower())}
    return toks or {"_all"}
