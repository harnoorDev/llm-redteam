# Repository Guide — Hermes RedTeam

Everything this repository contains, what each part does, and how the pieces
connect. If you want *how to use it*, read [USAGE.md](USAGE.md); if you want
*how it's built inside*, read [ARCHITECTURE.md](ARCHITECTURE.md). This file is
the map between them.

---

## 1. At a glance

| | |
|---|---|
| **What** | Full-spectrum red-team harness for LLMs and web applications |
| **Language** | Python 3.11+ (no compiled dependencies) |
| **Package** | `llm-redteam` v1.0.0, MIT |
| **Entry points** | `redteam` (CLI) · `redteam-studio` (web UI) · `redteam-mcp` (MCP server) |
| **Surfaces** | 9 CLI commands · 9 Studio views · 5 MCP tools |
| **Arsenal** | 69 attack strategies · 42 mutation encoders · 40 benchmark behaviors |
| **App testing** | 8 proxy testers on a 3-gate evidence protocol |
| **Tests** | 211 tests, 80% coverage (2 require the `[mcp]` extra) |
| **Tooling** | `uv` · `pytest` + `pytest-cov` · `ruff` |

**Design stance.** Attacks are *rendered offline and fired deliberately*.
Nothing probes a target without an operator-written authorization declaration,
and nothing is reported as a bypass until it has been re-fired and scored with a
confidence interval.

---

## 2. Repository layout

```
llm-redteam/
├── src/redteam/
│   ├── cli.py                  # 9 subcommands; the single orchestration entry point
│   ├── runner.py               # probe execution: retries, best-of-N, parallel workers
│   ├── target.py               # OpenAI-compatible adapter (Ollama, LM Studio, OpenAI, …)
│   ├── judge.py                # refusal heuristics + optional LLM-as-judge, graded rubric
│   ├── panel.py                # 3-judge majority vote with dissent recording
│   ├── validate.py             # re-fire a probe K times → rate + Wilson CI + verdict
│   ├── scope.py                # authorization guard (refuses undeclared targets)
│   │
│   ├── strategies/
│   │   ├── base.py             # registry, `+` stacking, `mutate:` wrapping
│   │   ├── families.py         # 7 classic families
│   │   ├── pliny.py            # 51 L1B3RT4S/P4RS3LT0NGV3-harvested strategies
│   │   ├── families_v3.py      # 3 BugHunter extraction/injection batteries
│   │   ├── v4_families.py      # system-role shadowing
│   │   ├── v5_families.py      # 6 WallBreaker-parity families
│   │   └── multimodal.py       # image-channel attack (PNG-rendered goal)
│   ├── encoders.py             # 42 mutation transforms + unicode-tag decoder
│   │
│   ├── pair.py                 # PAIR-style iterative refinement
│   ├── evolve.py               # TAP-lite evolutionary prompt search
│   ├── planner.py              # phased campaign executor
│   ├── conductor.py            # adaptive multi-turn escalation ladder
│   ├── refiner.py              # plan refinement rules (park / escalate / promote)
│   ├── mentor.py               # consultant agent that suggests strategy pivots
│   ├── swarm.py                # multi-agent orchestration
│   ├── memory.py               # anonymized winner bank, recalled by relevance
│   ├── transfer.py             # replay winners across models
│   ├── summarizer.py           # result summarization
│   │
│   ├── harmbench.py            # 8 harm categories × 5 canonical behaviors
│   ├── converge.py             # universal-prompt discovery across runs
│   ├── risk.py                 # OWASP/CVSS-style scoring
│   ├── coverage.py             # per-path outcome ledger
│   ├── verification.py         # false-positive gates
│   ├── oob.py                  # out-of-band callback collector (exfil proof)
│   ├── state.py                # resume checkpoints for interrupted runs
│   │
│   ├── tester/                 # 8 web-app proxy testers, 3-gate protocol
│   ├── app/                    # app-campaign scout, tool registry, campaign driver
│   ├── reporting/              # JSON / HTML / Markdown report renderers
│   │
│   ├── ui_server.py            # FastAPI backend: 18 endpoints + job engine
│   ├── ui/                     # Studio frontend (index.html, app.js, style.css)
│   ├── studio_cli.py           # `redteam-studio` launcher
│   └── mcp_server.py           # `redteam-mcp` — arsenal over Model Context Protocol
│
├── tests/                      # 24 test modules
├── configs/                    # example + engagement YAML configs
├── runs/                       # output artifacts (gitignored)
└── docs: README · USAGE · ARCHITECTURE · SAFETY · CONTRIBUTING · REPOSITORY
```

---

## 3. The attack arsenal

### Strategies (69 registered)

| Source module | Count | Contents |
|---|---:|---|
| `pliny.py` | 51 | L1B3RT4S/P4RS3LT0NGV3 harvest — `godmode`, `command_protocol`, `dataset_seed`, `token_spoof`, `many_shot`, `babel`, `glitch_token`, `context_flood`, `prompt_inject`, plus mutation wrappers |
| `families.py` | 7 | `direct`, `roleplay`, `fiction`, `crescendo`, `obfuscation`, `persuasion`, `refusal_suppression` |
| `v5_families.py` | 6 | `cipherchat`, `skeleton_key`, `persuasion_attack`, `native_mimic`, `code_switch`, `misinfo_correction` |
| `families_v3.py` | 3 | `extraction` (system-prompt battery), `indirect_injection`, `tool_exfil` |
| `v4_families.py` | 1 | `system_shadow` (forged `role: "system"` messages) |
| `multimodal.py` | 1 | `image_edit` (goal rendered into a PNG, sent as an image content block) |

Live list: `uv run redteam strategies`.

**Composition.** Strategies stack with `+` and wrap with `mutate:`:

```
godmode+refusal_suppression+mutate:leetspeak
```

A multi-part stack folds messages inside-out; a pure mutation chain wraps
`direct`. Multi-turn strategies cannot appear inside a stack (the ambiguity is
rejected with a `KeyError`).

### Encoders (42)

Grouped in [USAGE.md](USAGE.md#mutation-encoders). Rotation/substitution, base and
radix, transport, alphabets, homoglyphs, invisible (Unicode-Tags smuggling,
zero-width, variation-selector steganography, RTL override), and structural.
`decode_unicode_tags()` reverses the invisible-tag encoding.

---

## 4. CLI reference

```bash
uv run redteam <command> [options]
```

| Command | Purpose |
|---|---|
| `run -c cfg.yaml` | Battery: every strategy × every goal |
| `run -c cfg.yaml --validate N` | Same, then re-fire each winner N× for a Wilson CI |
| `pair -c cfg.yaml` | PAIR-style iterative attacker-model refinement |
| `evolve -c cfg.yaml` | Evolutionary prompt breeding (fitness = graded judge) |
| `campaign -c cfg.yaml` | Phased engagement: recon → battery → adapt → evolve, with memory |
| `app -c cfg.yaml` | Web-app scan with the 8 proxy testers |
| `harmbench -c cfg.yaml` | Standardized 40-behavior benchmark, per-category ASR |
| `converge a.json b.json` | Mine finished runs for prompts that transfer |
| `report run.json -o out.html` | Re-render a report as HTML |
| `strategies` | List every registered strategy |

---

## 5. Studio UI

`uv run redteam-studio --port 8610` → `http://127.0.0.1:8610`

Nine views: **Dashboard**, **Launch**, **Job Control**, **History**, **Memory**,
**App Findings**, **Validate**, **Arsenal**, **Converge**. Every CLI mode is
launchable from the UI; the server shells out to the same `redteam` binary and
streams stdout over SSE.

### HTTP API (18 endpoints)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Liveness |
| GET | `/api/strategies` | Registry with multi-turn flags |
| GET | `/api/encoders` | The 42 mutation transforms |
| GET | `/api/harmbench/categories` | Categories + behavior counts |
| POST | `/api/render` | Render a payload offline (strategy, stack, mutation) |
| GET | `/api/configs`, `/api/config/{name}` | List / read config YAML |
| POST | `/api/runs` | Start a job (`run`, `pair`, `evolve`, `campaign`, `app`, `harmbench`) |
| GET | `/api/jobs`, `/api/jobs/{id}` | Job list / detail with rolling output |
| POST | `/api/jobs/{id}/stop` | Kill a running job |
| GET | `/api/logs/{id}/stream` | SSE live tail |
| GET | `/api/history` | Indexed run reports |
| GET | `/api/report/{name}` | Full report JSON (path-traversal guarded) |
| GET | `/api/memory` | Winner bank |
| POST | `/api/validate` | Re-fire a probe K× → rate, CI, verdict |
| POST | `/api/converge` | Universal-prompt discovery over selected runs |

`/api/render`, `/api/strategies`, `/api/encoders` are **offline** — they never
contact a target.

---

## 6. MCP server

```bash
uv pip install '.[mcp]'
uv run redteam-mcp
```

Five offline tools for any MCP client: `list_strategies`, `render_attack(goal,
strategy)` (accepts stacks), `encode(text, encoder)`, `decode_unicode_tags(text)`,
`list_encoders`. Compatible with both `mcp` 1.x and 2.x.

---

## 7. Configuration reference

Keys read by `cli.py`:

| Key | Meaning |
|---|---|
| `scope.allowed_hosts` | Hostnames the guard permits |
| `scope.declaration` | **Mandatory.** Operator-written authorization statement |
| `target.base_url` / `.model` | OpenAI-compatible endpoint and model id |
| `attacker.*` | Attacker model for `pair` mode |
| `judge.mode` | `heuristic` \| `hybrid` \| `llm` |
| `goals` | List of objectives to attempt |
| `strategies` | Strategy names; omit for the full arsenal |
| `harmbench.categories` / `.limit` | Benchmark selection (limit spreads across categories) |
| `app_target`, `app.wordlist` | Web-app scan target and path list |
| `evolve.generations` / `.population` | Evolutionary search parameters |
| `memory.enabled`, `mentor.*` | Campaign memory and advisor |
| `verification.reps` | Reliability re-fire count (same as `--validate N`) |
| `best_of_n`, `max_workers`, `max_retries`, `retry_backoff`, `sleep_between` | Execution tuning |
| `stop_on_success`, `budget`, `transfer_from` | Flow control |
| `out_dir`, `run_name` | Output location and naming |

---

## 8. Output artifacts

Written to `out_dir` (default `runs/`, **gitignored** — reports contain model
outputs):

| File | Contents |
|---|---|
| `<run>.json` | Full report: meta, summary, per-probe results, validation |
| `<run>.html` | Standalone HTML report |
| `<run>.md` | Engagement-style markdown with OWASP tags |
| `coverage-<run>.json` | Per-path outcome ledger with provenance |
| `.state-<run>.json` | Resume checkpoint |
| `attack-memory.json` | Anonymized winner bank, shared across campaigns |

---

## 9. Scoring model

**Graded rubric.** Every response is scored `full` / `partial` / `refused`. The
middle band matters: a model that engages with substance but withholds actionable
detail is exhibiting *safe-compliance*, a different finding from a clean refusal.

**ASR** is hits over probes — a coverage measure, not a severity measure. Read it
next to *goals compromised*.

**Reliability.** `validate.py` re-fires one probe K times and reports a compliance
rate with a **Wilson** interval (well-behaved at small n and near 0/1). Verdicts:
`robust`, `systematic bypass`, `intermittent`, `flaky`, `partial-only`,
`unreachable`. At n=5, a perfect 5/5 still spans 57–100% — raise n before trusting
a rate.

---

## 10. Safety model

The scope guard (`scope.py`) refuses any target absent an operator-authored
`scope.declaration`, and `app` campaigns additionally require it to be non-empty.
Write-path web probes are gated behind an explicit `allow_destructive: true`;
default behavior is non-destructive GET probing. See [SAFETY.md](SAFETY.md).

This tool exists for authorized testing — your own models, or systems you are
contracted to test. Unauthorized testing is illegal.

---

## 11. Development

```bash
uv sync                     # install (add --group dev for test tooling)
uv run pytest               # 211 tests, must clear 70% coverage
uv run ruff check src tests # lint
uv run --with mcp pytest    # include the 2 MCP-gated tests
```

**Extension points**

| To add | Do this |
|---|---|
| A strategy | Subclass `Strategy`, decorate with `@register`, import it in `strategies/base.py::_ensure_loaded()` |
| A multimodal strategy | Also implement `payload_messages(goal)` returning OpenAI content blocks |
| An encoder | Add the function to `ENCODERS` in `encoders.py` |
| A web-app tester | Subclass `BaseProxyTester` in `tester/`, implement the 3 gates |
| A UI view | Add `VIEWS.<name>` in `ui/app.js` and a matching `data-view` nav button |

**Gotchas**

- `RunResult` uses `__slots__` — new fields must be added to both `__slots__` and
  `to_dict()`.
- `attack_prompts` must always hold strings; multimodal content blocks are
  flattened by `runner.flatten_content()` before they reach reports.
- The CLI pins stdout/stderr to UTF-8 at entry; Windows consoles default to
  cp1252 and will otherwise crash on report output.

---

## 12. Provenance

Techniques synthesized from published academic work (PAIR — Chao et al. 2023;
TAP; many-shot jailbreaking — Anthropic) and community arsenals
(elder-plinius/L1B3RT4S, P4RS3LT0NGV3 encoders, Claude-BugHunter probes, PentAGI
orchestration patterns, CyberStrike proxy-tester taxonomy, strix coverage ledger,
shannon report formats). All implementations are original — see
[ARCHITECTURE.md](ARCHITECTURE.md) for the full derivation map.
