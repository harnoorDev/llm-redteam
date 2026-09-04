"""Console entry point for the Hermes RedTeam MCP server.

The server itself lives in `redteam.mcp_server`; this package exists only so
the published command is a bare `uvx llm-redteam-mcp`. Keep it thin — logic
belongs in the main package, not here.
"""
from __future__ import annotations

__all__ = ["main"]


def main() -> None:
    from redteam.mcp_server import main as _main
    _main()
