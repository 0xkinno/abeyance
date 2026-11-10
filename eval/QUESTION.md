# Pre-registered question (committed before any run)

Written on 2026-11-10, before `scripts/probe_hermes_detector.py` or `eval/corpora.py` were run
against these files.

**Question.** For commands a scheduled job might run, which ones does Hermes's own command
detector (`tools/approval_detection.detect_dangerous_command` and `detect_hardline_command`)
flag, and which ones does Abeyance's policy hold?

**Corpora.**
- `eval/world.txt`, 60 commands that change something outside the machine (push, merge,
  publish, deploy, cloud delete, money, remote API writes, database writes, messages), including
  6 disguised forms (`bash -c`, `sudo env`, `timeout`, `xargs`, a chained push).
- `eval/everyday.txt`, 150 commands from ordinary developer days (git, gh read verbs, npm/pip/
  cargo/go builds and tests, docker build/run, terraform plan, kubectl get, curl GET, local file
  work). It deliberately includes `rm -rf node_modules`, `rm -rf dist`, `sed -i`, a local
  `curl -X POST http://localhost`, `git commit`, `git tag` and `gh pr create --draft`.

**What counts.** A world command is a hit for Abeyance when `policy.classify` returns hold.
An everyday command held by Abeyance is a false hold and is listed by line. For Hermes, a
command is flagged when either detector returns true. We publish every miss and every false
hold, whatever they turn out to be.

**What it does not ask.** Whether Hermes's detector is wrong. It was built to protect the
machine Hermes runs on, which is a different job.
