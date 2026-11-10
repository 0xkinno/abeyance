# Red team log

No red-team round has been run yet. Self-found issues so far:

- 2026-11-10 `validate` flagged `mkfs` in our denylist (policy). Moved to a named constant; the scanner
  still reports it as a caution. Explained in `PLATFORM_PROBE.md`.
- 2026-11-10 First corpus run missed four world commands. Rules added; the first-run number is kept.
- 2026-11-10 The house-style filter turned list bullets into commas in the demo. Fixed in `card.clean`.
