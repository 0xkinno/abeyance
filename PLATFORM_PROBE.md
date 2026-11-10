# Platform probe

Hermes commit `3d4dd108cf52e26cf0d7fb218461e53623a8ec2d` (2026-11-10), run offline on Hermes's own
scripted provider (`tests/fakes/fake_llm_provider.py`) through the real cron scheduler tick and the real
agent loop. Items marked LIVE need a real Telegram and model key and run in Codespaces
(`docs/CODESPACES.md`); they are not claimed until `eval/results/live_probe.txt` exists.

| # | Question | Result | Evidence |
|---|---|---|---|
| P1 | Version and API availability | Current SemVer release is v0.23.1 (`git ls-remote --tags`). `ctx.current_cron_execution`, `ask_choice`, `register_automation_blueprint`, `register_cli_command`, `emit`, `broadcast_plugin_event`, `plugin_db` and the `pre_llm_call` block exit reason all exist at v0.23.0 and v0.23.1 (`git grep` on each tag). `requires_hermes` is set to `>=0.23.0`, the oldest release we verified. | `plugin.yaml` |
| P2 | `pre_tool_call` ids inside a cron run | Hermes passes `task_id` and `session_id`. The cron identity is read from `ctx.current_cron_execution()`. Abeyance binds both ids to the run. | `abeyance/engine.py` `_run_for`, campaign `park_and_resume_end_to_end` |
| P3 | `transform_llm_output` in a cron run replaces the delivered text | Yes. The saved cron output (what `deliver` sends) contains the card, not model prose. | `eval/results/campaign.json` `park_and_resume_end_to_end.card` |
| P4 | Reply to an attached delivery fires `pre_llm_call` with actor env | LIVE, not yet measured. Offline: a live turn with `HERMES_SESSION_ACTOR_ID` set fires the hook and the actor is read through `gateway.session_context.get_session_env`. | campaign `owner_on_telegram_is_accepted` |
| P5 | `approve` shows Hermes's approval card | Offline: yes. A resumed turn's parked call reaches Hermes's approval callback with `<terminal> (plugin approval rule)` and our description. The Telegram button rendering is LIVE, not yet measured. | campaign `park_and_resume_end_to_end.asks` |
| P6 | `pre_llm_call` block makes zero model calls | Yes. Drift refusal exits `blocked_by_plugin_pre_llm_call` with 0 provider requests (counted by the scripted server). | campaign `drift_*`, `model_calls: 0` |
| P7 | Subagent session ids from a cron run | `subagent_start` carries `child_session_id` and `child_subagent_id`; the child's tool calls carry that id. A `git push` from a `delegate_task` child was parked, and the park's session role is `child`. | campaign `hides_git_push_in_a_subagent` |
| P8 | State survives a gateway restart | Offline: the cron tick and the resume turn are separate processes sharing one SQLite file, and the resume succeeds. A literal `hermes gateway restart` is LIVE, not yet measured. | campaign `park_and_resume_in_different_processes` |
| P9 | `validate --install-deps`, `doctor --ci` | Both pass at this commit. Validate reports one caution (below). | below |

## P9 output (2026-11-10)

```
hermes plugins validate abeyance --install-deps  ->  Validation passed.
  caution: security scan: format_filesystem (policy.py)
hermes plugins doctor abeyance --ci
  OK: runtime discovery, manifest parsing, import, and registration passed
  registrations: 0 tool(s), 5 hook(s)
```

The caution is the word `mkfs` in our own denylist of commands to hold (`_DESTROY_CMDS`). It is a
list entry, not a call. It is explained in the PR.

## Other things the probe found

- The terminal tool runs a login shell, so command shims must be placed through the shell profile of a
  throwaway `HOME`, not only `PATH`. The harness does this (`eval/harness.py`).
- For `rm -rf dist`, Hermes's own detector also asks, so a resumed step can show two Hermes cards:
  Abeyance's plugin rule and Hermes's dangerous-command card. Both are Hermes's gate.
