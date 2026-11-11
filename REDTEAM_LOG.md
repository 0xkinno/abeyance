# Red team log

## Round 1, 2026-11-10

Five fresh reviewers, each given the repo read-only and one role: usefulness, reliability and security,
honesty of claims, polish, catalog rules and creativity. None was clean. What was found, and what was done.

| Role | Found | Done |
|---|---|---|
| Reliability | Disguised steps ran unheld: `git -C . push`, `bash -lc`, `sudo -u root`, `nice -n 10`, a newline before `git push`, `gh api -f`, `npm -r publish`, `python -m twine`; tool names like `update_record` and `send_status` were allowed; `urllib` writes and `/work/../x` paths passed | Fixed in `policy.py`; `tests/test_hardening.py` |
| Reliability | A cron session or subagent could resume its own park; a stranger could probe which codes exist; an unknown platform naming a user counted as local; a scalar `owners` value split into digits | Fixed in `engine.py`; tests |
| Reliability | The ledger was permanent per command, so the nightly blueprint's `npm publish` would be blocked from night two | Ledger is now one entry per park; test |
| Reliability | A frozen run could still write memory; non-dict args crashed a cron call | Fixed; tests |
| Reliability | Drift compares against the folder recorded at park time, is checked at the resume message and not at execution, and only sees files the step names | Not changed; stated in the README promises table |
| Honesty | Stale claims: test count, "not opened yet", "not yet measured" restart, local times shown as UTC, Desktop listed as polish | Corrected; EVIDENCE.md now records the restart |
| Polish | Three "not yet" admissions above the fold, mismatched demo timing, a build-jargon comment in `plugin.yaml` | Fixed |
| Catalog | Held arguments are stored verbatim (a token in a command is stored with it); `git status` runs in the job folder | Disclosure updated in the README; the catalog entry text still needs the same line |
| Creativity | The policy is a pattern list tuned on its own corpus (56 of 60 untuned); the blueprint is a prompt template | Kept as is; the README already says 56 of 60 first run |

The 33-case campaign on a real Hermes ran before these fixes. The new tests cover them offline (101 pass).
Round 2 has not been run.

## Maintainer review, 2026-11-11

The catalog reviewer asked for the host-side git calls to be hardened (a repo-configured `core.fsmonitor` or filter driver could run with the host environment). Done in `drift.py`: minimal explicit environment, `-c core.fsmonitor=false -c core.hooksPath=/dev/null`, `stdin=DEVNULL`, `status` skipped when `filter.*` drivers exist. Tests: `tests/test_git_hardening.py`. When `status` is skipped, drift cannot see uncommitted changes; HEAD, branch, upstream and file hashes are still compared.
