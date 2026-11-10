# Thesis

- Name: Abeyance (a matter held, not dropped, until the person entitled to decide it decides).
- Moment: Ines, at 02:14, when her nightly job reaches `npm publish`.
- Action: the run stops at that step, keeps its work, asks her on her phone, and finishes from that step
  after her yes, once the repo is checked.
- One sentence: Abeyance makes Hermes's scheduled runs reliable enough to leave alone: at the one step a
  night job should not take by itself, the run waits for you, and finishes from that step when you say yes.
- Guarantee: a scheduled Hermes run does not take a world-changing step its owner has not seen, and does
  not throw away the work it did before that step.
- One card per run: the run freezes at its first held step. Reads after the park are allowed so the run
  can end cleanly; nothing else runs.
- Abstention: unknown commands are allowed unless a user `hold` rule matches. The false-hold rate on the
  everyday corpus is published (2 of 150).
- Memory: Abeyance stores parks, steps (summaries, 300-character excerpts) and events. It never writes
  Hermes memory or skills.
- Delete test: without `pre_tool_call` the step runs; without `pre_llm_call` a resumed step runs against
  a changed repo; without `transform_llm_output` the owner gets model prose; without the `subagent_start`
  binding a push in a subagent runs unasked; without `plugin_db` a restart loses the step.
