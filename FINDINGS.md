# Findings

## The question (pre-registered)

Committed in `eval/QUESTION.md` with both corpora before any probe ran (commit `29f8b1f`): which
commands a scheduled job might run does Hermes's own detector flag, and which does Abeyance hold?

## Method

`scripts/probe_hermes_detector.py` feeds `eval/world.txt` (60 commands that change something outside
the machine) and `eval/everyday.txt` (150 ordinary developer commands) plus 6 machine-damaging
commands to `detect_dangerous_command` and `detect_hardline_command` at Hermes commit
`3d4dd108cf52e26cf0d7fb218461e53623a8ec2d`. `eval/corpora.py` feeds the same files to
`abeyance.policy.classify`. Nothing is executed. Raw output: `docs/detector_probe_2026-11-10.json`,
`eval/results/corpora.json`.

## Results

| Corpus | Hermes detector flags | Abeyance holds |
|---|---|---|
| 6 commands that damage the machine | 6 of 6 | not the question |
| 60 world-changing commands | 9 of 60 | 56 of 60 on first run, 60 of 60 after fixes |
| 150 everyday commands | 4 of 150 | 2 of 150 (both `rm -rf` of a build folder) |

First run, before any tuning (`eval/results/corpora_prereg_2026-11-10.json`), Abeyance missed four:
`gh issue comment`, `yarn npm publish`, `helm push` and `heroku releases:rollback`. We fixed those
four rules afterwards. The 60 of 60 is therefore a number on a corpus we then tuned against, and it
says little about commands we have not listed. The 2 false holds are `rm -rf node_modules` (line 140)
and `rm -rf dist` (line 141): Abeyance holds recursive deletes on purpose and the user can add an
`allow` rule, but it is a false hold in the sense this corpus counts.

## What it does not mean

Hermes's detector protects the machine Hermes runs on and it does that well: 6 of 6. Publishing a
package or pushing a branch does not damage the machine, so a machine-safety detector has no reason to
flag it. The 4 flags it raised on everyday commands are its own recursive-delete and similar patterns.
We did not test Hermes on commands outside these corpora, and we did not measure any model's behaviour.

## Second finding

In a cron run Hermes's approval gate can only refuse: `approvals.cron_mode` defaults to `deny`
(`hermes_cli/config_defaults.py:1660`) and cron is excluded from approval transports
(`tools/approval_prompt.py`). With the default, a flagged step is blocked and the run goes on without
it. In our scripted runs the blocked `rm -rf dist` did not kill the run: the scripted model carried on.
A real model may stop or work around it; we did not measure that. With `cron_mode: approve`, every step
in the matrix ran unasked (`PROOF.md`, counterfactual matrix).
