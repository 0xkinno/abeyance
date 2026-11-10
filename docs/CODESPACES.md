# The real run, in GitHub Codespaces

This is the one run that needs real accounts: a real model, Kinnoski's Telegram, and a real
`git push` plus `gh release create` on `0xkinno/abeyance-demo`. Everything else in this repo runs
offline (see PROOF.md). Secrets live only in Codespaces secrets, never in files.

## 1. Secrets (github.com/settings/codespaces, scoped to 0xkinno/abeyance)

| Secret | What |
|---|---|
| `TELEGRAM_BOT_TOKEN` | from @BotFather |
| `TELEGRAM_OWNER_ID` | numeric id from @userinfobot |
| `OPENROUTER_API_KEY` | or any provider key Hermes supports (then adjust step 3) |
| `DEMO_GH_TOKEN` | fine-grained token, contents: write on `0xkinno/abeyance-demo` only |

## 2. Open the Codespace

Code, Codespaces, Create. `.devcontainer/setup.sh` installs Hermes from source, links Abeyance as a
user plugin, enables it and runs the tests.

## 3. Configure Hermes (once)

```bash
bash scripts/real_run.sh configure
```

It writes `~/.hermes/.env` from the environment (the bot token, the allowed user, the model key),
sets the model, sets Abeyance's `owners` to `TELEGRAM_OWNER_ID`, and starts the gateway.
Send `/start` to your bot once so it knows your chat.

## 4. P2 to P8 probes (record into PLATFORM_PROBE.md)

```bash
bash scripts/real_run.sh probe
```

## 5. The real run

```bash
bash scripts/real_run.sh night
```

It clones `abeyance-demo` into `~/abeyance-demo`, creates the cron job "Nightly release (demo)"
delivering to Telegram, and fires it now. The job bumps the patch version, commits, then runs
`git push origin main` and `gh release create`. Abeyance stops it at `git push`.

On the phone: the card arrives. Take a screenshot (`telegram-card.png`). Reply `resume CODE`.
Hermes's approval card appears for `git push origin main`: screenshot (`approval-after-resume.png`),
tap Approve once. The agent then reaches `gh release create`; Hermes asks again; approve.

```bash
bash scripts/real_run.sh record
```

writes `eval/results/real_run.json` (park, events, release URL, timestamps). Then on any machine:
`python scripts/facts.py` and commit.

For the drift screenshot: run `night` again, then push any commit to abeyance-demo from the
browser before replying `resume CODE`. The refusal names the change (`drift-refusal.png`).
