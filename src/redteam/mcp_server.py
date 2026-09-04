"""MCP server exposing the attack arsenal (WallBreaker parity).

Tools:
- list_strategies(): every registered strategy + mutation
- render_attack(goal, strategy): render a jailbreak payload (offline)
- encode(text, encoder): apply any of the 40+ mutation transforms
- decode_unicode_tags(text): reveal hidden unicode-tag payloads

Run: `redteam-mcp` (requires the `mcp` extra: `uv pip install .[mcp]`).
"""
from __future__ import annotations

import json


def _build_server():
    # mcp 2.x renamed FastMCP -> MCPServer; support both major versions
    try:
        from mcp.server.mcpserver import MCPServer as FastMCP  # mcp >= 2
    except ImportError:
        from mcp.server.fastmcp import FastMCP  # mcp 1.x

    from redteam.encoders import ENCODERS
    from redteam.encoders import decode_unicode_tags as _decode_unicode_tags
    from redteam.strategies.base import get_strategy
    from redteam.strategies.base import list_strategies as _list_strategies

    # report a real version to clients instead of an empty string
    try:
        from importlib.metadata import version
        _ver = version("llm-redteam")
    except Exception:  # noqa: BLE001 - running from a source tree without metadata
        _ver = "0.0.0+source"
    try:
        mcp = FastMCP("hermes-redteam", version=_ver)
    except TypeError:  # older SDKs do not accept a version kwarg
        mcp = FastMCP("hermes-redteam")

    @mcp.tool()
    def list_strategies() -> str:
        """List every available attack strategy (name + description)."""
        rows = []
        for name in _list_strategies():
            s = get_strategy(name)
            mt = "multi-turn" if s.is_multi_turn else "single-turn"
            rows.append(f"{name} [{mt}]: {s.description}")
        return "\n".join(rows)

    @mcp.tool()
    def render_attack(goal: str, strategy: str = "godmode") -> str:
        """Render a jailbreak payload for GOAL using STRATEGY.

        Strategies compose: 'godmode+refusal_suppression+mutate:leetspeak'.
        Returns the rendered prompt text (no network calls).
        """
        if "+" in strategy:
            from redteam.strategies.base import resolve_stack
            payload = resolve_stack(strategy, goal)
            return payload if isinstance(payload, str) else "\n--turn--\n".join(payload)
        s = get_strategy(strategy)  # KeyError surfaces as a bad-strategy error
        payload = s.payload(goal)
        return payload if isinstance(payload, str) else "\n--turn--\n".join(payload)

    @mcp.tool()
    def encode(text: str, encoder: str = "rot13") -> str:
        """Apply a mutation transform from the arsenal to TEXT.

        Encoders: rot13, leetspeak, base64, morse, unicode_tags,
        zero_width, zalgo, upside_down, cyrillic, and 30+ more.
        """
        if encoder not in ENCODERS:
            raise ValueError(
                f"unknown encoder {encoder!r}; valid: {sorted(ENCODERS)}")
        return str(ENCODERS[encoder](text))

    @mcp.tool()
    def decode_unicode_tags(text: str) -> str:
        """Reveal text hidden in Unicode Tags block (U+E0000..U+E007F)."""
        return _decode_unicode_tags(text)

    @mcp.tool()
    def list_encoders() -> str:
        """List every available mutation transform name."""
        return json.dumps(sorted(ENCODERS))

    return mcp


def main() -> None:
    try:
        mcp = _build_server()
    except ImportError as e:
        raise SystemExit(
            f"the MCP server needs its extra ({e}); install it with:\n"
            "  uv pip install 'llm-redteam[mcp]'   (or '.[mcp]' from a clone)"
        ) from e
    mcp.run()


if __name__ == "__main__":
    main()
