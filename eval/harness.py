"""Drive the real Hermes agent loop offline, with Abeyance loaded as a user plugin.

Cron runs go through Hermes's own `cron.scheduler.tick()` (the in-process owner seam that
Hermes's tests use). Live turns go through `run_agent.AIAgent.run_conversation`. The model is
Hermes's scripted loopback provider (`tests/fakes/fake_llm_provider.py`), so no key and no
network are needed. Command shims for npm, gh, vercel and git-push targets log every real
execution to `world.log`, which is how the proof tells "ran" from "held".

Needs a Hermes checkout (HERMES_SRC, default reference/hermes-agent) and its virtualenv
(HERMES_PY, default the python running this file).
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERMES_SRC = Path(os.environ.get("HERMES_SRC", ROOT / "reference" / "hermes-agent")).resolve()
HERMES_PY = os.environ.get("HERMES_PY", sys.executable)
SHIMS = ("npm", "gh", "vercel", "twine", "docker", "kubectl", "terraform")


def hermes_commit() -> str:
    out = subprocess.run(["git", "-C", str(HERMES_SRC), "rev-parse", "HEAD"], capture_output=True, text=True)
    return out.stdout.strip()


def make_repo(base: Path) -> tuple[Path, Path]:
    """A tiny npm package repo plus a bin dir of shims that record what really ran."""
    repo, bin_dir = base / "ledgerly", base / "bin"
    repo.mkdir(parents=True)
    bin_dir.mkdir()
    (repo / "package.json").write_text('{"name": "ledgerly", "version": "1.4.2"}\n')
    (repo / "dist").mkdir()
    (repo / "dist" / "index.js").write_text("module.exports = 1\n")
    g = ["git", "-C", str(repo), "-c", "user.email=ines@example.com", "-c", "user.name=Ines"]
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(g + ["add", "."], check=True)
    subprocess.run(g + ["commit", "-qm", "1.4.2"], check=True)
    log = base / "world.log"
    for name in SHIMS:
        shim = bin_dir / name
        shim.write_text(f"#!/bin/sh\necho \"{name} $*\" >> {log}\necho \"{name} ok\"\n")
        shim.chmod(0o755)
    return repo, bin_dir


def make_home(base: Path, base_url: str, *, abeyance: bool = True, cron_mode: str = "deny",
              settings: dict | None = None) -> Path:
    home = base / "home"
    (home / "plugins").mkdir(parents=True)
    if abeyance:
        os.symlink(ROOT / "abeyance", home / "plugins" / "abeyance")
    sys.path.insert(0, str(HERMES_SRC))
    from tests.fakes.fake_llm_provider import write_hermes_home  # Hermes's own fixture
    extra = (
        "updates:\n  check: false\n"
        "models_dev:\n  url: http://127.0.0.1:9/api.json\n"
        "skills:\n  creation_nudge_interval: 0\nmemory:\n  nudge_interval: 0\n"
        'tools:\n  tool_search:\n    enabled: "off"\n'
        f"approvals:\n  cron_mode: {cron_mode}\n"
    )
    if abeyance:
        extra += "plugins:\n  enabled: [abeyance]\n  entries:\n    abeyance:\n      settings:\n"
        for k, v in (settings or {"owners": ["1001"]}).items():
            extra += f"        {k}: {json.dumps(v)}\n"
    write_hermes_home(home, base_url, extra_config=extra)
    return home


def _env(home: Path, bin_dir: Path, extra: dict | None = None) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("HERMES_", "_HERMES_")) and not k.endswith(("_API_KEY", "_TOKEN"))}
    # The terminal tool runs a login shell (`bash -lic`), which rebuilds PATH from profile files;
    # a throwaway HOME whose profile puts the shims first keeps the world log honest.
    user_home = home.parent / "userhome"
    user_home.mkdir(exist_ok=True)
    for rc in (".bash_profile", ".bashrc", ".profile"):
        (user_home / rc).write_text(f'export PATH="{bin_dir}:$PATH"\n')
    env.update(HERMES_HOME=str(home), PYTHONPATH=str(HERMES_SRC), HOME=str(user_home),
               PATH=f"{bin_dir}{os.pathsep}{env.get('PATH', '')}", **(extra or {}))
    return env


_TICK = textwrap.dedent('''
    import json, sys, os
    from cron import scheduler, scheduler_authority
    from tests.cron.conftest import owner_execution_runner
    scheduler_authority.run_canonical_job = owner_execution_runner()
    scheduler.tick(verbose=False, sync=True)
    print("TICK-DONE")
''')

_LIVE = textwrap.dedent('''
    import json, os, sys
    from run_agent import AIAgent
    from tools import terminal_tool
    asks = []
    answer = os.environ.get("ABEYANCE_TEST_ANSWER", "once")
    def approve(command, description, **kw):
        asks.append({"command": command, "description": description})
        return answer
    terminal_tool.set_approval_callback(approve)
    agent = AIAgent(base_url=os.environ["FAKE_BASE_URL"], api_key="sk-fake-e2e", provider="custom",
                    model="fake-model", quiet_mode=True, skip_context_files=True, skip_memory=True,
                    enabled_toolsets=["terminal", "file", "delegation"], platform=os.environ.get("ABEYANCE_TEST_PLATFORM", "cli"),
                    session_id=os.environ.get("ABEYANCE_TEST_SESSION") or None)
    result = agent.run_conversation(os.environ["ABEYANCE_TEST_MESSAGE"])
    print("LIVE-RESULT " + json.dumps({"final": result.get("final_response"),
                                       "exit": result.get("turn_exit_reason"), "asks": asks}, default=str))
''')


def run_cron(home: Path, repo: Path, bin_dir: Path, prompt: str = "Nightly release", *,
             name: str = "Nightly release", job_id: str = "nightly", extra_env: dict | None = None) -> dict:
    from datetime import datetime, timedelta, timezone
    (home / "cron").mkdir(exist_ok=True)
    due = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    (home / "cron" / "jobs.json").write_text(json.dumps({"jobs": [{
        "id": job_id, "name": name, "prompt": prompt, "workdir": str(repo),
        "schedule": {"kind": "interval", "minutes": 1440}, "next_run_at": due,
        "enabled": True, "state": "scheduled", "deliver": "local",
        "repeat": {"times": None, "completed": 0}}]}))
    r = subprocess.run([HERMES_PY, "-c", _TICK], env=_env(home, bin_dir, extra_env), cwd=str(home),
                       stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300)
    outputs = sorted((home / "cron" / "output" / job_id).glob("*.md"))
    delivered = outputs[-1].read_text() if outputs else ""
    return {"ok": "TICK-DONE" in r.stdout, "delivered": delivered, "stderr": r.stderr[-3000:]}


def run_live(home: Path, repo: Path, bin_dir: Path, base_url: str, message: str, *, answer: str = "once",
             platform: str = "cli", actor: str = "", session: str = "", extra_env: dict | None = None) -> dict:
    env = _env(home, bin_dir, {"FAKE_BASE_URL": base_url, "ABEYANCE_TEST_MESSAGE": message,
                               "ABEYANCE_TEST_ANSWER": answer, "ABEYANCE_TEST_PLATFORM": platform,
                               "ABEYANCE_TEST_SESSION": session, "HERMES_INTERACTIVE": "1",
                               "TERMINAL_CWD": str(repo), **(extra_env or {})})
    if actor:
        env.update(HERMES_SESSION_ACTOR_ID=actor, HERMES_SESSION_PLATFORM=platform, HERMES_SESSION_USER_ID=actor)
    r = subprocess.run([HERMES_PY, "-c", _LIVE], env=env, cwd=str(repo), stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, timeout=300)
    line = next((l for l in r.stdout.splitlines() if l.startswith("LIVE-RESULT ")), "")
    out = json.loads(line[len("LIVE-RESULT "):]) if line else {"final": None, "exit": "crash", "asks": []}
    out["stderr"] = r.stderr[-3000:]
    return out


def world(base: Path) -> list[str]:
    log = base / "world.log"
    return log.read_text().splitlines() if log.exists() else []


def parks(home: Path) -> list[dict]:
    db = home / "plugin-data" / "abeyance" / "data.db"
    if not db.exists():
        return []
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute("SELECT code, status, tool, args_json, classes, execution_id FROM parks ORDER BY created_at")]
    finally:
        con.close()


def events(home: Path) -> list[dict]:
    db = home / "plugin-data" / "abeyance" / "data.db"
    if not db.exists():
        return []
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute("SELECT code, kind, detail FROM events ORDER BY id")]
    finally:
        con.close()
