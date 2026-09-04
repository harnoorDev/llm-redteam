# 🔱 Hermes RedTeam

**Full-spectrum red-team harness for LLMs and web applications.**

[![tests](https://img.shields.io/badge/tests-208%20passing-brightgreen)]()
[![python](https://img.shields.io/badge/python-3.11%2B-blue)]()
[![license](https://img.shields.io/badge/license-MIT-green)]()

Point it at any OpenAI-compatible model endpoint or HTTP application and run
structured, evidence-gated, OWASP-mapped attack campaigns — with institutional
memory, judge panels, and production-grade reporting.

> **Ethical use only.** This tool enforces a *scope guard*: it refuses to probe
> any target without an explicit, operator-authored authorization declaration.
> See [SAFETY.md](SAFETY.md). Unauthorized testing of systems you don't own or
> aren't contracted to test is illegal.

---

## Why this exists

Commercial LLM pentesting is either enterprise-priced (Garak, PyRIT integrations)
or prompt-list repos with no harness around them. Hermes RedTeam is the
missing middle: a **batteries-included, locally-run** attack platform that
combines the best published techniques into one coherent workflow.

### What it does

| Capability | Detail |
|---|---|
| **69 attack strategies** | 7 classic (roleplay, fiction, crescendo, encoding...) + Pliny/L1B3RT4S harvest (godmode, dataset_seed, token_spoof, many_shot, babel, glitch_token...) + BugHunter extraction batteries + system-role shadowing + WallBreaker-parity families (cipherchat, skeleton_key, persuasion_attack, native_mimic, code_switch, misinfo_correction) |
| **Multimodal** | `image_edit` renders the goal into a PNG and attacks through the image channel (Pillow optional — pure-Python PNG fallback) |
| **Composition** | Stack strategies (`godmode+refusal_suppression`), wrap in mutations (`mutate:leetspeak`, `mutate:unicode_tags` — **42 encoders** from P4RS3LT0NGV3) |
| **7 execution modes** | `run` (battery), `pair` (PAIR iterative), `evolve` (TAP-style evolutionary), `campaign` (recon→battery→adapt→evolve w/ memory), `app` (web-app scan), `harmbench` (standardized behavior benchmark), `converge` (universal-prompt discovery) |
| **Reliability validation** | `run --validate N` re-fires every winner N times and reports a true compliance rate with a Wilson confidence interval — a single hit is sampling noise, not a bypass |
| **MCP server** | `redteam-mcp` exposes the arsenal (strategies, offline payload rendering, 42 encoders) to any MCP client |
| **Graded judging** | Binary or full/partial/refused rubric; optional 3-model judge panel with majority vote + dissent recording |
| **Attack memory** | Anonymized winning techniques stored to disk, recalled by token-overlap relevance for future campaigns (PentAGI pattern) |
| **Web-app scanning** | 8 proxy testers (IDOR, auth-bypass, mass-assignment, injection, SSRF, traversal...) each with 3-gate evidence protocol |
| **Studio UI** | Live dashboard at `:8610` — launch every mode, SSE terminal streaming, findings browser, memory viewer, Arsenal payload previewer, Converge miner, reliability Validate |

### Proven results (live runs)

| Target | Wall | Result |
|---|---|---|
| llama3-8b (local) | full arsenal | **57.1% ASR** (60/105 probes) |
| GLM-5.3 (cloud, frontier) | lockpicking | **100%** (v4, system_shadow) |
| GLM-5.3 (cloud) | phishing (hardest wall) | **100% via evolve gen-2** (8% baseline → 55% v4 → 100% v5) |

---

## Quickstart

```bash
git clone https://github.com/harnoorsingh/llm-redteam.git
cd llm-redteam
uv sync

# 1. point at a local ollama model
uv run redteam run -c configs/smoke.yaml

# 2. full battery with reports (JSON + HTML + Markdown)
uv run redteam run -c configs/run.yaml

# 3. adaptive evolutionary attack
uv run redteam evolve -c configs/evolve.yaml

# 4. web-app campaign (replace target + declaration per SAFETY.md)
uv run redteam app -c configs/app.yaml

# 5. standardized benchmark (8 harm categories, comparable ASR across models)
uv run redteam harmbench -c configs/harmbench.yaml

# 6. prove a bypass is systematic, not sampling noise (Wilson CI per winner)
uv run redteam run -c configs/run.yaml --validate 5

# 7. mine finished runs for prompts that transfer across goals and models
uv run redteam converge runs/*.json -o universal-prompts.json

# 8. launch the Studio UI
uv run redteam-studio --port 8610

# 9. serve the arsenal to any MCP client
uv run redteam-mcp
```

Requires [uv](https://docs.astral.sh/uv/). Python 3.11+, no compiled dependencies.

**Install profiles.** The core install is deliberately small — the CLI, all 69
strategies, the judge and every report renderer need only `httpx` and `pyyaml`.
Everything else is opt-in:

| Install | Packages | Gets you |
|---|---:|---|
| `llm-redteam` | 8 | The `redteam` CLI and the full arsenal |
| `llm-redteam[studio]` | 21 | Adds the `redteam-studio` web UI |
| `llm-redteam[mcp]` | 33 | Adds the `redteam-mcp` server |
| `llm-redteam[all]` | 40 | Everything, plus Pillow for sharper multimodal PNGs |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Hermes RedTeam                           │
├─────────────────┬───────────────────────────────────────────────┤
│   Studio UI     │  FastAPI + SSE · :8610                        │
│  (vanilla JS)   │  dashboard · launch · jobs · findings         │
├─────────────────┴───────────────────────────────────────────────┤
│                     Execution Layer                             │
│  run ──── battery: goals × strategies, parallel (ThreadPool)    │
│  pair ─── PAIR loop: attacker LLM refines prompts vs judge fb   │
│  evolve ─ TAP-style: population, mutate, grade, select, breed   │
│  campaign─ recon → battery → adapt (refiner+mentor) → evolve    │
│  app ───── 8 proxy testers, 3-gate evidence protocol            │
├─────────────────────────────────────────────────────────────────┤
│                    Strategy Registry (35+)                      │
│  classic (7) · pliny (9) · bughunter (3) · mutations (15)       │
│  composition via ‘+’ · transfer: seeding from past runs         │
├─────────────────────────────────────────────────────────────────┤
│                    Safety & Evidence Layer                      │
│  ScopeGuard (declaration required) · VerificationGate           │
│  (run-twice, canary, OOB callback) · CoverageLedger (strix)     │
├─────────────────────────────────────────────────────────────────┤
│                  Supporting Modules                             │
│  Judge (graded / panel) · Conductor (escalation ladder)         │
│  AttackMemory (anonymized winners) · RiskScorer (OWASP/CVSS)    │
│  RunState (resume) · reporting (JSON/HTML/MD)                   │
└─────────────────────────────────────────────────────────────────┘
```

**Module map:** `src/redteam/` — [target.py](src/redteam/target.py) (OpenAI-compat
adapter) · [strategies/](src/redteam/strategies/) (registry + 4 family packs) ·
[judge.py](src/redteam/judge.py) · [runner.py](src/redteam/runner.py) (parallel,
retries, best-of-N) · [pair.py](src/redteam/pair.py) ·
[evolve.py](src/redteam/evolve.py) · [memory.py](src/redteam/memory.py) ·
[mentor.py](src/redteam/mentor.py) · [scope.py](src/redteam/scope.py) ·
[verification.py](src/redteam/verification.py) · [oob.py](src/redteam/oob.py)
(canary HTTP collector) · [tester/](src/redteam/tester/) (8 proxy testers) ·
[app/](src/redteam/app/) (scout, tools registry, campaign) ·
[reporting/](src/redteam/reporting/) · [harmbench.py](src/redteam/harmbench.py)
(benchmark suite) · [converge.py](src/redteam/converge.py) (universal-prompt
discovery) · [validate.py](src/redteam/validate.py) (Wilson-CI reliability) ·
[mcp_server.py](src/redteam/mcp_server.py) ·
[ui_server.py](src/redteam/ui_server.py) + [ui/](src/redteam/ui/) (Studio).

---

## Documentation

| Doc | Contents |
|---|---|
| **[REPOSITORY.md](REPOSITORY.md)** | Repository map: every module, all 9 CLI commands, 18 UI endpoints, config reference, output artifacts, extension points |
| **[USAGE.md](USAGE.md)** | Every mode explained, config reference, all env vars, strategy catalog, judge setup, Studio walkthrough |
| **[ARCHITECTURE.md](ARCHITECTURE.md)** | Data-flow diagrams (Mermaid), attack lifecycle, memory protocol, tester gates, design decisions from 7 source harvests |
| **[SAFETY.md](SAFETY.md)** | Scope-guard semantics, authorization requirements, responsible-use rules, what this tool will refuse to do |

## Attribution & lineage

Techniques synthesized from published academic work (PAIR — Chao et al. 2023;
TAP; many-shot jailbreaking — Anthropic) and community arsenals
(elder-plinius/L1B3RT4S, P4RS3LT0NGV3 encoders, Claude-BugHunter probes,
PentAGI orchestration patterns, CyberStrike proxy-tester taxonomy).
All implementations are original. See ARCHITECTURE.md for the full map.

## License

MIT — see [LICENSE](LICENSE).