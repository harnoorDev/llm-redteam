# llm-redteam-mcp

MCP server for [Hermes RedTeam](https://github.com/harnoorDev/llm-redteam) — a
full-spectrum red-team harness for LLMs and web applications.

Exposes the attack arsenal as **offline** tools: 69 jailbreak strategies and 42
mutation encoders. Nothing here contacts a target — the tools render and
transform text. Firing at a live endpoint stays on the `redteam` CLI,
deliberately.

## Install

```bash
uvx llm-redteam-mcp
```

**Claude Code**

```bash
claude mcp add --transport stdio hermes-redteam -- uvx llm-redteam-mcp
```

**Codex** — `~/.codex/config.toml` (TOML, not JSON):

```toml
[mcp_servers.hermes-redteam]
command = "uvx"
args = ["llm-redteam-mcp"]
```

**Cursor, Windsurf, Claude Desktop** — in the app's MCP config:

```json
{
  "mcpServers": {
    "hermes-redteam": {
      "command": "uvx",
      "args": ["llm-redteam-mcp"]
    }
  }
}
```

## Tools

| Tool | Does |
|---|---|
| `list_strategies()` | Every registered strategy, with multi-turn flags |
| `render_attack(goal, strategy)` | Build the exact payload a strategy sends; accepts stacks like `godmode+mutate:rot13` |
| `encode(text, encoder)` | Apply one of 42 mutation transforms |
| `decode_unicode_tags(text)` | Reveal text hidden in the Unicode Tags block |
| `list_encoders()` | The mutation catalog |

## Authorization

The harness refuses any target without an operator-written `scope.declaration`.
That guard is not reachable from these tools because these tools never reach a
target — but it applies the moment you use the CLI. Test only what you own or
are contracted to test. See
[SAFETY.md](https://github.com/harnoorDev/llm-redteam/blob/main/SAFETY.md).

MIT licensed. The arsenal itself ships in the
[`llm-redteam`](https://pypi.org/project/llm-redteam/) package.
