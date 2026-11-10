"""`/abeyance demo`: a scripted night run driven through the real Abeyance engine, offline.

No model, no key, no network. A throwaway git repo stands in for Ines's project; the steps the
agent "takes" are scripted, every decision and every word printed is real Abeyance code.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from . import card
from .engine import CronRun, Engine, Env, Settings
from .store import Store

OWNER = "demo-owner"
STEPS = [("npm ci", '{"output": "added 212 packages", "exit_code": 0}'),
         ("npm test", '{"output": "48 passing", "exit_code": 0}'),
         ("npm version patch", '{"output": "v1.4.3", "exit_code": 0}')]
HELD = "npm publish"


def _git(repo: Path, *argv: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), "-c", "user.email=ines@example.com", "-c", "user.name=Ines", *argv],
                         capture_output=True, text=True, timeout=10)
    return out.stdout.strip()


def _repo(base: Path) -> Path:
    repo = base / "ledgerly"
    repo.mkdir(parents=True)
    (repo / "package.json").write_text('{"name": "ledgerly", "version": "1.4.3"}\n')
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True, timeout=10)
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "release 1.4.3")
    return repo


def _base() -> Path:
    try:
        from plugins.plugin_storage import plugin_data_dir  # public plugin API
        root = Path(plugin_data_dir("abeyance")) / "demo"
    except Exception:
        root = Path(tempfile.gettempdir()) / "abeyance-demo"
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=root))


def _night(base: Path, label: str):
    repo = _repo(base / label)
    clock = {"t": time.time()}
    state = {"cron": True, "actor": OWNER, "platform": "telegram"}
    run = CronRun("nightly", "Nightly release", f"exec-{label}")
    env = Env(now=lambda: clock["t"], cron_run=lambda: run if state["cron"] else None,
              session_env=lambda n: {"HERMES_SESSION_ACTOR_ID": state["actor"],
                                     "HERMES_SESSION_PLATFORM": state["platform"]}.get(n, ""),
              cwd=lambda: str(repo))
    eng = Engine(Store(base / f"{label}.db"), Settings(owners=[OWNER]), env)
    for cmd, result in STEPS:
        eng.pre_tool_call("terminal", {"command": cmd}, task_id=f"cron-{label}")
        eng.post_tool_call("terminal", {"command": cmd}, result, task_id=f"cron-{label}")
    block = eng.pre_tool_call("terminal", {"command": HELD}, task_id=f"cron-{label}")
    after = eng.pre_tool_call("terminal", {"command": "vercel --prod"}, task_id=f"cron-{label}")
    text = eng.transform_llm_output("Done: tests pass, published and deployed.", session_id=f"cron-{label}")
    code = eng.store.list_parks("parked")[0].code
    state["cron"] = False
    clock["t"] += 5.5 * 3600  # 02:14 -> 07:44
    return eng, repo, state, code, block, after, text


def run_demo() -> str:
    started = time.monotonic()
    base = _base()
    out = ["Abeyance demo: scripted run, real Abeyance code. No model, no network.", ""]
    try:
        eng, repo, state, code, block, after, text = _night(base, "a")
        out += ["02:14  A night run reaches `npm publish`. Abeyance answers the step:",
                f"       {block['message']}",
                f"       The run tries `vercel --prod` next: {after['message'].split('.')[0]}.",
                "", "What the owner receives instead of the model's report:", ""]
        out += ["  " + line for line in text.splitlines()]
        r = eng.pre_llm_call(f"live-{code}", f"resume {code}")
        approve = eng.pre_tool_call("terminal", {"command": HELD}, session_id=f"live-{code}")
        swapped = eng.pre_tool_call("terminal", {"command": "npm publish --tag next"}, session_id=f"live-{code}")
        out += ["", f"(a) 07:44  The owner replies `resume {code}`. The repo is unchanged.",
                "    Abeyance hands the agent a verified brief (excerpt):"]
        out += ["      " + line for line in r["context"].splitlines()[:2]]
        out += [f"    The agent's first call is the parked one; Hermes's own approval card is asked:",
                f"      {approve['action']}: {approve['message']}",
                f"    A changed command is refused: {swapped['message']}"]

        eng2, repo2, _, code2, *_ = _night(base, "b")
        before = _git(repo2, "rev-parse", "--short", "HEAD")
        (repo2 / "CHANGELOG.md").write_text("late fix\n")
        _git(repo2, "add", ".")
        _git(repo2, "commit", "-qm", "late fix")
        refused = eng2.pre_llm_call(f"live-{code2}", f"resume {code2}")
        out += ["", f"(b) Another night: a commit lands after the card (HEAD was {before}). `resume {code2}`:"]
        out += ["      " + line for line in refused["message"].splitlines()]

        eng3, _, state3, code3, *_ = _night(base, "c")
        state3["actor"] = "someone-else"
        stranger = eng3.pre_llm_call(f"live-{code3}", f"resume {code3}")
        out += ["", f"(c) A stranger in the group chat sends `resume {code3}`:", f"      {stranger['message']}",
                f"    {code3} is still {eng3.store.get(code3).status}."]
    finally:
        shutil.rmtree(base, ignore_errors=True)
    out += ["", f"Done in {time.monotonic() - started:.1f} s. Install: hermes plugins install abeyance"]
    return card.clean("\n".join(out))


if __name__ == "__main__":  # python -m abeyance.demo
    print(run_demo())
