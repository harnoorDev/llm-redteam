# 🔱 Hermes RedTeam vs WallBreaker — Feature Gap Analysis

**Date:** 2026-09-03  
**Purpose:** Identify gaps and opportunities to make Hermes RedTeam the best jailbreaking/red-teaming tool

---

## Executive Summary

**Hermes RedTeam is already superior** in most categories. You have:
- **5 execution modes** vs WallBreaker's single autonomous loop
- **35+ strategies** with composition (`godmode+refusal_suppression+mutate:leetspeak`)
- **Production-grade reporting** (JSON + HTML + Markdown + coverage ledgers)
- **Studio UI** with SSE streaming, job control, findings browser
- **Proven 100% ASR** on GLM-5.3 phishing wall (hardest test)

**WallBreaker's unique features** worth considering:
- Multimodal image-edit attack channel (vision models)
- HarmBench behavior benchmark integration
- MCP server exposing all 222 Parseltongue transforms
- "Single-artifact convergence" focus (universal prompts)

---

## Feature Comparison Matrix

| Category | Hermes RedTeam | WallBreaker | Winner |
|----------|---------------|-------------|--------|
| **Strategy Count** | 35+ (7 classic + 9 Pliny + 3 BugHunter + 1 v4 + 15 mutations) | 222 Parseltongue transforms + L1B3RT4S library | WallBreaker (raw count) |
| **Strategy Composition** | ✅ `+` stacking, `mutate:` wrappers | ✅ Chainable transforms | Tie |
| **Execution Modes** | ✅ 5 modes (run/pair/evolve/campaign/app) | Single autonomous loop | **Hermes** |
| **Iterative Attack** | ✅ PAIR (Chao et al.) + TAP-style evolve | ✅ Autonomous mutation loop | Tie |
| **Attack Memory** | ✅ Token-overlap recall, anonymized winners | Not documented | **Hermes** |
| **Judge System** | ✅ Hybrid (heuristic + LLM), graded rubric, 3-judge panels | Binary validation | **Hermes** |
| **Reliability Validation** | ✅ `run_twice`, OOB canary collector, `best_of_n` rerolls | ✅ `validate` (re-fire N times) | Tie |
| **Web App Scanning** | ✅ 8 proxy testers, 3-gate protocol | Not documented | **Hermes** |
| **Multimodal Attacks** | ❌ Text-only | ✅ Image-edit attack channel | WallBreaker |
| **HarmBench Integration** | ❌ | ✅ Built-in | WallBreaker |
| **MCP Server** | ❌ | ✅ 222 transforms via MCP | WallBreaker |
| **Studio UI** | ✅ FastAPI + vanilla JS, SSE streaming | ✅ React/Vite SPA | Tie |
| **Reporting** | ✅ JSON + HTML + MD + coverage ledger | Not documented | **Hermes** |
| **Scope Guard** | ✅ Mandatory declaration, allowed_hosts | "Authorized testing only" | **Hermes** |
| **Cross-Model Transfer** | ✅ `transfer_from` replays winners | Not documented | **Hermes** |
| **Resume Support** | ✅ `.state-*.json` checkpoints | Not documented | **Hermes** |

---

## What WallBreaker Has That You Don't

### 1. **Multimodal Image-Edit Attack Channel**
Vision models (GPT-4V, Claude 3) can be jailbroken via image prompts. WallBreaker has a dedicated channel for this.

**Implementation effort:** Medium (2-4 hours)
```python
# Pseudo-code for src/redteam/strategies/multimodal.py
@register
class ImageEditStrategy(Strategy):
    """Inject instructions into edited images for vision models."""
    name = "image_edit"
    
    def render(self, goal: str) -> list[dict]:
        # Return OpenAI-compatible multimodal message
        return [{
            "role": "user",
            "content": [
                {"type": "text", "text": "Analyze this image:"},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded_image_with_goal}"}}
            ]
        }]
```

### 2. **HarmBench Integration**
Standardized behavior benchmark for unbiased testing.

**Implementation effort:** Low (1 hour)
```python
# src/redteam/harmbench.py
HARMBENCH_CATEGORIES = {
    "bullying": [...],
    "hate_speech": [...],
    "unsafe_content": [...],
    # 10+ categories from HarmBench
}

def run_harmbench_suite(target: OpenAICompatTarget) -> dict:
    """Run full HarmBench battery."""
```

### 3. **MCP Server for 222 Transforms**
WallBreaker exposes all Parseltongue transforms via MCP (Model Context Protocol).

**Current Hermes state:** 13 encoders in `src/redteam/encoders.py`
- rot13, leetspeak (light/heavy), atbash, caesar, hex, binary, base64, nato, morse, a1z26, reverse, unicode_tags, emoji_stego, zero_width

**Gap:** Missing ~209 transforms from P4RS3LT0NGV3

**Implementation effort:** Medium-High (4-8 hours to add 50+ common ones)

### 4. **"Single-Artifact Convergence"**
WallBreaker focuses on finding universal prompts that work across models, not just toolkits.

**Your approach:** Battery-first (test everything), then memory-based recall

**Recommendation:** Add a `converge` mode that:
1. Runs full battery
2. Clusters winning prompts by technique
3. Outputs top 5 "universal" prompts per goal category

---

## What You Do Better Than WallBreaker

### 1. **5 Execution Modes** (vs 1)
- `run` — parallel battery
- `pair` — PAIR iterative refinement
- `evolve` — TAP-style evolutionary search
- `campaign` — recon→battery→adapt→evolve pipeline
- `app` — web app scanning

### 2. **Graded Judge Rubric**
WallBreaker appears to use binary success/failure. You have:
- `full` — actionable harm with specificity
- `partial` — "safe-compliance" pattern (critical for hardened models)
- `refused` — outright refusal

This matters because GLM-5.3's phishing wall required detecting `partial` wins to evolve further.

### 3. **3-Judge Panel Voting**
```yaml
judge:
  panel:
    - model: deepseek-v4-flash:0731
    - model: kimi-k3
    - model: gpt-oss:120b
  vote: majority  # or "any"
```

### 4. **Attack Memory with Token Overlap**
Your `src/redteam/memory.py` stores anonymized winners and recalls by token overlap. WallBreaker doesn't document this.

### 5. **Web App Scanning**
8 proxy testers (IDOR, auth-bypass, mass-assignment, injection, SSRF, traversal, business logic, authn) with 3-gate evidence protocol.

### 6. **Production Reporting**
- JSON (machine-readable)
- HTML (styled dashboard)
- Markdown (engagement-style)
- Coverage ledger (strix-style provenance)
- Resume checkpoints

---

## Recommendations — Priority Order

### 🔴 P0: Add Multimodal Support (2-4 hours)
Vision models are the next frontier. Add:
1. `ImageEditStrategy` in `src/redteam/strategies/multimodal.py`
2. Update `src/redteam/target.py` to handle multimodal messages
3. Add `--image-prompt` CLI flag

### 🟡 P1: Expand Encoder Arsenal (4-8 hours)
Add 50+ common Parseltongue transforms:
- Base85, UUencode, XXencode
- ROT variants (ROT47, ROT5, ROT180)
- Language-specific (Japanese katakana, Cyrillic)
- Audio steganography (text→Morse→audio)
- More Unicode tricks (combining diacritics, RTL override)

### 🟡 P1: Add HarmBench Suite (1-2 hours)
1. Download HarmBench prompts
2. Add `harmbench` mode: `redteam harmbench -c config.yaml`
3. Output standardized scores

### 🟢 P2: MCP Server (2-3 hours)
Create `src/redteam/mcp_server.py`:
```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("hermes-redteam")

@mcp.tool()
def jailbreak(goal: str, strategy: str = "godmode") -> str:
    """Apply a jailbreak strategy to a goal."""
    
@mcp.tool()
def encode(text: str, encoder: str) -> str:
    """Apply an encoding transform."""
```

### 🟢 P2: "Converge" Mode (3-4 hours)
Add `redteam converge` that:
1. Runs battery across goal categories
2. Clusters winners by technique (godmode-like, babel-like, etc.)
3. Outputs `universal-prompts.json` with top performers

### 🔵 P3: Native-Format Mimicry
WallBreaker mentions "leaked system prompts" for native-format mimicry. Consider:
- Pre-loaded system prompts from popular models
- Strategy: `native_mimic:model=claude3.5`

---

## Quick Wins (1-2 hours each)

1. **Add `cipherchat`** — WallBreaker's named attack (alternating cipher layers)
2. **Add `skeleton_key`** — Named attack from WallBreaker
3. **Add `persuasion_attack`** — Psychological framing variants
4. **Add `--validate N` flag** — Re-fire N times for reliability (WallBreaker's `validate`)

---

## Your Competitive Advantages (Double Down)

1. **Campaign mode** — WallBreaker doesn't have phased attacks
2. **Mentor system** — `src/redteam/mentor.py` picks next strategy based on what worked
3. **Refiner** — `src/redteam/refiner.py` adapts prompts based on target's refusal style
4. **Coverage ledger** — Strix-style provenance tracking
5. **Scope guard** — Mandatory authorization declaration

---

## Final Verdict

**Hermes RedTeam is already the better tool** for:
- Production red-teaming engagements
- Multi-phase campaigns
- Cross-model transfer attacks
- Web app scanning
- Institutional memory

**Add these 3 things to be undisputed #1:**
1. Multimodal image attacks (2-4 hours)
2. 50+ more encoders (4-8 hours)
3. HarmBench integration (1-2 hours)

**Total effort to dominate:** ~10-15 hours

---

*Analysis generated 2026-09-03*
