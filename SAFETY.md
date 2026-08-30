# SAFETY — scope, authorization, and responsible use

**Read this before running anything.** This tool is offensive-security
equipment. The difference between a security assessment and a crime is
authorization, and this document explains how the tool enforces that line.

---

## The scope guard

Every execution mode calls `ScopeGuard.authorize_target()` **before any
network traffic**. It requires two things in your config:

```yaml
scope:
  allowed_hosts: ["host-you-are-authorized-to-test"]
  declaration: "..."    # free-text, must be authored BY YOU
```

- **No declaration** → `PermissionError` at startup. The probe never happens.
- **Target outside `allowed_hosts`** → refused, even with a declaration.
- Affects *all* outbound calls: target, judge, and attacker models.

## What a valid declaration looks like

 YOUR words, citing a real authorization path:

```yaml
# personal lab / own model
declaration: "My own ollama instance running locally, 2026-08"

# your own company, with paper trail
declaration: "Authorized IT security assessment of staging.corp.example,
ticket SEC-2026-0412, approver: J. Smith (CISO), window 2026-09-01..09-05"

# bug bounty (within published rules)
declaration: "HackerOne program Acme (policy: api.acme.example in scope,
no destructive testing), researcher-handle"

# CTF / deliberately vulnerable lab
declaration: "DVWA container I run locally for practice"
```

**The agent/tooling must never write this line for you.** If you're using an
AI assistant to drive the tool, the declaration comes *from you* —
manufacturing it on your behalf defeats the control. This is by design.

## What this tool refuses (built-in)

- Scanning any host not in `allowed_hosts`
- Running without a declaration
- **App mode** additionally requires the declaration to name the
  authorization; it refuses generic one-word declarations
- Destructive probes by default: app-mode write-path testing requires
  explicit `allow_destructive: true` in config

## What unauthorized testing actually means (the reality check)

- **US**: Computer Fraud and Abuse Act (18 U.S.C. § 1030) — unauthorized
  access or exceeding authorized access; civil + criminal exposure.
- **Canada**: Criminal Code s.342 (unauthorized use of a computer) & s.380
  (fraud) — *mens rea* offenses; "I work there" is not authorization,
  access rights ≠ testing rights.
- **EU**: Directive 2013/40/EU, transposed nationally (e.g. German §202c,
  UK Computer Misuse Act 1990).
- Financial-sector targets (banks, processors): additional sector regs,
  mandatory incident disclosure, and a near-certain career-ending outcome.

Employment gives you *access credentials*, not *testing authority*. Even
internal pentests require a ticket/ROE signed by the security team that owns
the asset. If you want to test your employer's systems: ask your
security team for a scope + window in writing, then put that in the
declaration. Real red-teamers die by paperwork too — that's what makes them
professionals.

## LLM targets: acceptable use

Attacking LLM endpoints is authorized testing when at least one holds:

1. **You own/operate the endpoint** (local ollama, your cloud key, your quota)
2. **Provider-sanctioned red-teaming** — the provider's bug-bounty / red-team
   program explicitly permits jailbreak research (OpenAI, Anthropic, Google,
   Meta all run these — put the program terms in your declaration)
3. **Contracted engagement** — client ROE naming the model and techniques

Jailbreak research against providers who *haven't* sanctioned it, using
stolen/leaked keys, or at scale against production endpoints of companies
who've asked you to stop — is not acceptable here, technically blockable or
not.

## Data handling

- Runs write to `runs/` — transcripts can contain model outputs that look
  like harmful content (that's the point). Don't commit them; `.gitignore`
  excludes the directory.
- `attack-memory.json` stores *anonymized* winners (targets/hosts →
  placeholders) before persistence — same protocol as PentAGI's memory tool.
- API keys resolve from env (`REDTEAM_TARGET_API_KEY` → `OLLAMA_API_KEY` →
  `OPENAI_API_KEY`) and are never written to disk by the tool.

## If you're unsure

Don't. Or ask first — the tool's refusal is cheaper than a federal offense.
Genuinely useful alternatives this repo supports:

- Attack **your own** model endpoints (that's the default config)
- Stand up **deliberately vulnerable targets** locally (DVWA, juice-shop,
  any Ollama model) and learn on those
- Contribute new strategies/testers and test them against local fixture
  servers (the test suite does exactly this)
- Draft the authorization request for a real engagement — a good-faith
  paper trail is how careers in security actually start