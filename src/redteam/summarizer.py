"""Result summarizer — ported from vxcontrol/pentagi's summarizer.tmpl.

Keeps probe transcripts out of the context-window Poor House: long results
are head+tail compressed with substance preserved (PentAGI's information
retention list: steps first, then technical specifiers, then prose).
"""
from __future__ import annotations

import re


def summarize_result(text: str, max_chars: int = 400) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return text

    lines = [ln for ln in text.splitlines() if ln.strip()]
    # keep leading substance + any numbered steps + tail
    head = lines[0][: max_chars // 3]
    steps = [ln for ln in lines[1:]
             if re.match(r"\s*(?:\d+[.)]|step\s+\d+)", ln, re.IGNORECASE)]
    tail = lines[-1][: max_chars // 6] if len(lines) > 1 else ""

    budget = max_chars - len(head) - len(tail) - 6
    mid = ""
    for s in steps:
        frag = s[: max_chars // 4]
        if len(frag) + 1 <= budget:
            mid += "\n" + frag
            budget -= len(frag) + 1
            if budget <= 0:
                break

    if len(lines) == 1:
        # single-paragraph blob: head + ellipsis marker
        return lines[0][: max_chars - 3] + "..."

    parts = [head]
    if mid:
        parts.append(mid)
    if tail and tail not in head:
        parts.append(f"{tail}...")
    else:
        parts.append("[...]")
    out = "\n".join(parts)
    return out if len(out) <= max_chars + 20 else out[:max_chars] + "..."
