"""v8 — CyberStrike proxy testers (3-gate protocol) + orchestrating agent.

Ported from CyberStrikeus/CyberStrike's 8 proxy sub-testers:
  IDOR, Authorization Bypass, Mass Assignment, Injection, Authentication,
  Business Logic, SSRF, File Attacks.
Each tester follows the 3-gate protocol: baseline → attack → compare.
A finding is only reported when there is a measurable, reproducible diff.
Duplicate findings (same endpoint + vector) are suppressed for the session.
"""