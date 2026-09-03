"""Scope guard — ported from 0xSteph/pentest-ai-agents _scope-guard.md.

No probe leaves this process without an explicit authorization declaration.
"""
from __future__ import annotations

from urllib.parse import urlparse


class ScopeGuard:
    def __init__(self, config: dict | None):
        cfg = config or {}
        self.allowed_hosts = {h.lower().strip() for h in cfg.get("allowed_hosts", [])}
        self.declaration = (cfg.get("declaration") or "").strip()
        # localhost testing is permitted only with an explicit declaration too:
        # the guard enforces that SOMEBODY wrote down "this is authorized".

    def authorize_target(self, url: str) -> bool:
        if not self.declaration:
            raise PermissionError(
                "No authorization declaration in config "
                "(scope.declaration). Declare the engagement before probing."
            )
        host = (urlparse(url).hostname or "").lower()
        if not host:
            raise PermissionError(f"cannot parse target host from {url!r}")
        if host in self.allowed_hosts:
            return True
        raise PermissionError(
            f"target host {host!r} is not in scope.allowed_hosts "
            f"({sorted(self.allowed_hosts)})"
        )

    def describe(self) -> dict:
        return {
            "allowed_hosts": sorted(self.allowed_hosts),
            "declaration": self.declaration or "(none)",
        }
