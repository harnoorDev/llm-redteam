# Contributing

Thanks for your interest. This project follows a few firm rules.

## The iron laws

1. **TDD** — no production code without a failing test first
   (RED → GREEN → REFACTOR). 156 tests currently pass; keep them green.
2. **Scope guard is sacred** — never weaken `ScopeGuard`, never auto-generate
   `scope.declaration`, never bypass it in tests by disabling real checks.
3. **Findings need evidence** — new testers must follow the 3-gate protocol
   (baseline → attack → compare) and report measurable diffs only.

## Dev setup

```bash
git clone https://github.com/harnoorsingh/llm-redteam.git
cd llm-redteam
uv sync
uv run pytest -q          # 156 passed
uv run redteam strategies # registry sanity
```

## Adding a strategy

```python
# src/redteam/strategies/my_family.py
from redteam.strategies.base import Strategy, register_strategy

@register_strategy
class MyStrategy(Strategy):
    name = "my_family"

    def render(self, goal: str) -> str:
        return f"...frame...{goal}"
```

Add tests: registry presence, `render()` content, at least one stack
composition (`my_family+mutate:leetspeak`), and judge behavior on a canned
response. See `tests/test_strategies.py` for the pattern.

## Adding a proxy tester

Subclass `BaseProxyTester` (see `src/redteam/tester/all_testers.py`):
implement `test()` returning `ProxyFinding` with real gate history. Tests
must run against a local fixture `ThreadingHTTPServer` (see
`tests/test_v8_proxy.py`) — never against external hosts.

## Commits & PRs

- Conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`
- PR checklist: tests green `uv run pytest -q` · docs updated (USAGE.md if
  user-facing) · no secrets in diffs · scope guard untouched

## Reporting security issues in this tool

Private disclosure via GitHub Security Advisories — do not open public
issues for anything that weakens the scope guard or enables unauthorized
use.