# TASK.md: Abeyance

Mark `[x]` only when done and verified. Order is by dependency. Details: `ABEYANCE_BUILD_INSTRUCTION.md`.

## Phase 0. Repo, rails, references
- [x] Create public repo `0xkinno/abeyance` (MIT); unzip `abeyance-starter.zip` at its root
- [x] `git config user.name 0xkinno` and noreply email; verify no AI trailers in `git log`
- [x] Clone all references into `reference/`; `git check-ignore reference` prints `reference`
- [ ] Push; `ci` and `no-claude-attribution` workflows green on GitHub
- [ ] Fork `NousResearch/hermes-agent` to `0xkinno/hermes-agent` (no PR yet)
- [ ] Create `0xkinno/abeyance-demo` (tiny npm package repo for the real run)

## Phase 1. Probe and finding
- [x] Install Hermes from `reference/hermes-agent` in a venv with a throwaway `HERMES_HOME`
- [x] P1 version and API availability; set `requires_hermes` in `plugin.yaml`
- [x] P2 `pre_tool_call` kwargs inside a cron run
- [x] P3 `transform_llm_output` replaces delivered cron output
- [ ] P4 reply to an attached cron delivery fires `pre_llm_call` with actor env
- [ ] P5 `approve` directive shows Hermes's approval card on Telegram
- [x] P6 `pre_llm_call` block makes zero model calls
- [x] P7 subagent child session ids from a cron run
- [ ] P8 state survives `hermes gateway restart`
- [x] P9 `validate --install-deps` and `doctor --ci` run (record output)
- [x] `PLATFORM_PROBE.md` written with commands, outputs, dates
- [x] Commit corpora first (`eval/world.txt` 60 lines, `eval/everyday.txt` 150 lines), then run the probe
- [x] `FINDINGS.md` written (pre-registered question, method, results, what it does not mean)

## Phase 2. Real wiring
- [x] Session binding for every id Hermes passes in cron (from P2, P7)
- [x] Card delivery path confirmed (P3) or fallback implemented
- [ ] Resume path confirmed end to end (P4, P5) on CLI, Telegram, Desktop
- [x] Fail closed in cron on internal error; unchanged behaviour in live chats
- [x] Events emitted (`plugin.abeyance.changed`) on every transition
- [ ] `validate` and `doctor --ci` clean

## Phase 3. Surfaces
- [x] `hermes abeyance` CLI: list, show, deny, test, facts, demo
- [x] `/abeyance demo` offline in about 5 s (unchanged resume, drift refusal, stranger refusal)
- [ ] `/abeyance deny` with `ask_choice` confirmation where supported
- [x] Blueprint "Nightly release that waits for you"
- [x] `dashboard/plugin_api.py`: GET parks, GET park, POST deny, GET facts
- [x] `desktop/plugin.js`: chip, page, Resume via composer.submit, Drop, inline card
- [x] Desktop surface check passes (`validate` desktop surface)

## Phase 4. Proof and break campaign
- [x] `PROOF_PLAN.md` committed before running
- [x] Counterfactual matrix (default deny, approve mode, Abeyance) on a real Hermes
- [x] World corpus held rate, misses named
- [x] Everyday corpus false-hold rate, every false hold listed
- [x] Drift cases: commit, file edit, branch switch, folder deleted
- [x] Authority cases: stranger, empty owners on chat, forged webhook text
- [x] Replay: double resume, two chats at once
- [x] Expiry
- [x] Disguises: bash -c, sudo env, $(...), xargs, eval, timeout, execute_code subprocess
- [x] Misbehaving model: changed command, other held step first, repeat done step, push in subagent, calls after park
- [ ] Gateway restart between park and resume
- [x] Fault switch `ABEYANCE_FAULT` in cron and live
- [ ] Real run: Telegram card, `resume`, Hermes approval, real `git push` + `gh release create` on abeyance-demo
- [x] Model calls per park and per drift refusal counted
- [x] `scripts/facts.py` writes `docs/FACTS.json`; `--check` in CI
- [ ] `EVIDENCE.md` with screenshots, timestamps, release URL

## Phase 5. Docs and assets
- [x] README per section 13 (first screen: person, step, one sentence)
- [x] `SDK_SURFACE.md` with file:line in our code and in Hermes, versions, "not used, so not claimed"
- [x] `PROOF.md`, `PROGRESS.md`, `MILESTONES.md`, `DESIGN.md`, `JUDGE.md`
- [ ] `assets/banner.png` and four real screenshots
- [x] `check_copy.py` clean; numbers match FACTS everywhere

## Phase 6. Optional landing page
- [ ] `site/` static page on Vercel per DESIGN.md (only if Phase 5 is green)
- [ ] Playwright Chromium check at 390, 768, 1440 px; zero console errors; contrast AA

## Phase 7. Red team, list, submit
- [ ] Five-role judge red team; `REDTEAM_LOG.md`; repeat until a clean round
- [ ] Ask Kinnoski, then open catalog PR from the fork (`plugin-catalog/abeyance.yaml`, pinned SHA)
- [ ] Video under 90 s recorded and approved
- [ ] Ask Kinnoski, then post on X tagging @NousResearch
- [ ] Ask Kinnoski, then submit Typeform (PR link + X link); save confirmation
- [ ] Final SHA bump in the PR if needed (version bumped, screenshot URLs re-pinned)
- [ ] Tag the submitted commit; freeze
