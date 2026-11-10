---
name: abeyance
description: How scheduled Hermes jobs behave with Abeyance installed, and how to write cron prompts that park cleanly and resume well.
---

# Abeyance

When a cron job reaches a step that publishes, pushes, merges, deploys, pays, sends a message,
deletes in the cloud, writes a database or destroys local work, Abeyance stops that step and
the run ends with a card to the owner. Nothing after that step runs.

When the owner replies `resume CODE`, Abeyance checks the world is the one they were shown
(git HEAD, branch, uncommitted changes, the files the step touches). If anything changed it
refuses and names the change. If not, the agent's first action must be the exact parked call,
and Hermes asks the owner to confirm it with its own approval card.

## Writing a job that parks well

- Put read-only and reversible work first (fetch, build, test), the held step last.
- Make each step one command, so the card shows exactly what will happen.
- Say in the prompt what "done" looks like, so the resumed turn can finish and report.

## When you are the resumed turn

- Run the approved call first, unchanged. Any other held call is blocked until it has run.
- Do not repeat steps listed as already done. Abeyance blocks exact repeats.
- Report the result in plain words.
