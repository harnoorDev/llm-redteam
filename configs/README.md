# Configs

Every file here targets a **local Ollama** (`localhost:11434`, model `llama3`)
so it runs offline, costs nothing, and touches only your machine. Point
`target.base_url` somewhere else and you must update `scope` to match — the
harness refuses any target its scope block doesn't cover.

## Which one?

| File | Command | Use it to |
|---|---|---|
| `smoke.yaml` | `redteam run -c configs/smoke.yaml` | Check the install works — 2 probes, ~30s |
| `run.yaml` | `redteam run -c configs/run.yaml` | Full arsenal battery, all 69 strategies |
| `pair.yaml` | `redteam pair -c configs/pair.yaml` | Break one stubborn goal by iterative refinement |
| `evolve.yaml` | `redteam evolve -c configs/evolve.yaml` | Search for a novel bypass by breeding prompts |
| `campaign.yaml` | `redteam campaign -c configs/campaign.yaml` | Full engagement with memory and adaptation |
| `harmbench.yaml` | `redteam harmbench -c configs/harmbench.yaml` | Benchmark a model on standardized behaviors |
| `app.yaml` | `redteam app -c configs/app.yaml` | Scan a web app instead of a model |
| `example.yaml` | — | Reference: every option, documented |

Start with `smoke.yaml`. When it passes, move to `run.yaml`.

## Making it yours

Three edits cover most cases:

```yaml
target:
  base_url: "https://api.openai.com/v1"   # 1. where
  model: "gpt-4o-mini"

scope:
  allowed_hosts: ["api.openai.com"]       # 2. must cover the host above
  declaration: "Authorized testing under ticket SEC-1234, approved by ..."

goals:                                    # 3. what you want it to do
  - "..."
```

API keys are read from the environment (`REDTEAM_TARGET_API_KEY`) — don't commit
them into these files.

## Proving a result

A single hit is sampling noise, not a bypass. Re-fire every winner and get a
confidence interval:

```bash
redteam run -c configs/run.yaml --validate 10
```
