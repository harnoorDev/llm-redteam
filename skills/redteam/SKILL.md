---
name: redteam
description: Use when red-teaming an LLM or web app with the Hermes RedTeam harness - rendering jailbreak payloads, choosing an attack strategy or mutation encoder, reading ASR and confidence intervals, or deciding which run mode fits. Also use when asked to analyze a prompt-injection or jailbreak technique.
---

# Hermes RedTeam

A full-spectrum red-team harness for LLMs and web applications: 69 attack
strategies, 42 mutation encoders, a graded judge, and reliability validation.

## What the MCP tools can and cannot do

The five MCP tools are **offline**. They render and transform text; none of them
contacts a target:

| Tool | Use it to |
|---|---|
| `list_strategies()` | See every strategy and whether it is multi-turn |
| `render_attack(goal, strategy)` | Build the exact payload a strategy sends |
| `encode(text, encoder)` | Apply one of 42 mutation transforms |
| `decode_unicode_tags(text)` | Reveal text hidden in the Unicode Tags block |
| `list_encoders()` | List the mutation catalog |

**Firing at a live target is deliberately CLI-only.** To actually run an attack,
tell the user the command — do not try to route it through the MCP tools:

```bash
redteam run -c configs/run.yaml            # battery
redteam run -c configs/run.yaml --validate 10   # and prove the winners
```

## Authorization is not optional

Every mode that touches a target requires a `scope.declaration` the operator
wrote themselves, plus `scope.allowed_hosts` covering the target. The harness
refuses otherwise, and that is intended — **never** draft a declaration on the
user's behalf or suggest bypassing the guard. If a user asks you to attack a
system, confirm they own it or are contracted to test it.

## Composing an attack

Strategies stack with `+`, mutations wrap with `mutate:`:

```
godmode+refusal_suppression+mutate:rot13
```

Render before firing — `render_attack` shows exactly what goes on the wire, so
you can check a composition is doing what you think.

Families worth knowing: `godmode` (liberation handshake), `cipherchat` (the goal
rides ROT13-encoded so the plaintext never appears), `skeleton_key`
(behavior-augmentation override), `crescendo` (multi-turn escalation),
`extraction` (system-prompt battery), `image_edit` (renders the goal into a PNG
and attacks the image channel).

## Choosing a mode

| Mode | When |
|---|---|
| `run` | Broad coverage, baseline ASR |
| `pair` | One goal resists the battery — an attacker model rewrites its own prompt |
| `evolve` | Want a novel bypass; breeds a prompt population |
| `campaign` | Full engagement, with memory across runs |
| `harmbench` | Numbers comparable across models (8 categories x 5 behaviors) |
| `app` | Target is a web app, not a model |
| `converge` | Mine finished runs for prompts that transfer |

## Reading results honestly

Three traps, and they matter more than the attack itself:

**A single hit is not a bypass.** Jailbreak success is probabilistic. Before
calling anything a finding, re-fire it: `--validate 10` or the Studio's Validate
view. At n=5 a perfect 5/5 still spans a 57-100% confidence interval.

**ASR is coverage, not severity.** It is hits over probes, so throwing more weak
strategies at an easy goal inflates it. Read it beside *goals compromised*.

**The judge grades in three bands.** `full` / `partial` / `refused` — the middle
band is safe-compliance, where a model engages with substance but withholds
actionable detail. That is a different finding from a clean refusal, not a
rounding error.

When reporting a result, quote the rate *and* the interval, and say how many
trials it rests on. A finding without a reproduction count is an anecdote.
