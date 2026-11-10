import subprocess, time
import pytest
from abeyance.engine import Engine, Env, Settings, CronRun
from abeyance.store import Store

class Clock:
    def __init__(self): self.t = 1_800_000_000.0
    def __call__(self): return self.t

@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "package.json").write_text('{"name":"ledgerly","version":"1.4.3"}')
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.email=a@b", "-c", "user.name=t", "commit", "-qm", "init"], check=True)
    return tmp_path

def make(repo, cron=True, owners=("42",), platform="telegram", actor="42"):
    clock = Clock(); state = {"cron": cron, "actor": actor, "platform": platform}
    run = CronRun("job1", "Nightly release", "exec1")
    env = Env(now=clock, cron_run=lambda: run if state["cron"] else None,
              session_env=lambda n: {"HERMES_SESSION_ACTOR_ID": state["actor"], "HERMES_SESSION_PLATFORM": state["platform"]}.get(n, ""),
              cwd=lambda: str(repo))
    return Engine(Store(":memory:"), Settings(owners=list(owners)), env), clock, state

def park_one(e):
    assert e.pre_tool_call("terminal", {"command": "npm ci"}, task_id="cron-s") is None
    e.post_tool_call("terminal", {"command": "npm ci"}, '{"exit_code":0}', task_id="cron-s")
    d = e.pre_tool_call("terminal", {"command": "npm publish"}, task_id="cron-s")
    assert d["action"] == "block" and "is parked" in d["message"]
    return e.store.list_parks("parked")[0]

def test_park_freeze_card(repo):
    e, clock, st = make(repo)
    p = park_one(e)
    assert e.pre_tool_call("terminal", {"command": "git push"}, task_id="cron-s")["action"] == "block"   # frozen
    assert e.pre_tool_call("read_file", {"path": "x"}, task_id="cron-s") is None                        # reads still ok
    out = e.transform_llm_output("I published it!", session_id="cron-s")
    assert f"resume {p.code}" in out and "npm publish" in out and "\u2014" not in out

def test_resume_binds_exact_step(repo):
    e, clock, st = make(repo); p = park_one(e); st["cron"] = False
    r = e.pre_llm_call("chat-s", f"resume {p.code.lower()}", platform="telegram")
    assert "context" in r and "npm publish" in r["context"]
    assert e.pre_tool_call("terminal", {"command": "npm publish --tag next"}, task_id="chat-s")["action"] == "block"
    d = e.pre_tool_call("terminal", {"command": "npm publish"}, task_id="chat-s")
    assert d["action"] == "approve"                                     # Hermes's own gate asks the owner
    e.post_tool_call("terminal", {"command": "npm publish"}, '{"exit_code":0}', task_id="chat-s")
    assert e.store.get(p.code).status == "executed"
    assert e.pre_tool_call("terminal", {"command": "npm publish"}, task_id="chat-s")["action"] == "block"  # exactly once

def test_drift_refuses(repo):
    e, clock, st = make(repo); p = park_one(e); st["cron"] = False
    (repo / "package.json").write_text('{"name":"ledgerly","version":"9.9.9"}')
    r = e.pre_llm_call("chat-s", f"resume {p.code}", platform="telegram")
    assert r["action"] == "block" and "package.json changed" in r["message"]
    assert e.store.get(p.code).status == "drifted"

def test_head_moved_refuses(repo):
    e, clock, st = make(repo); p = park_one(e); st["cron"] = False
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@b", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "x"], check=True)
    r = e.pre_llm_call("chat-s", f"resume {p.code}")
    assert r["action"] == "block" and "HEAD moved" in r["message"]

def test_stranger_expiry_replay(repo):
    e, clock, st = make(repo); p = park_one(e); st["cron"] = False
    st["actor"] = "999"
    assert "only the job's owner" in e.pre_llm_call("chat-s", f"resume {p.code}")["message"]
    st["actor"] = "42"
    assert "context" in e.pre_llm_call("chat-s", f"resume {p.code}")
    assert "already" in e.pre_llm_call("chat-2", f"resume {p.code}")["message"]          # single use
    e2, clock2, st2 = make(repo); p2 = park_one(e2); st2["cron"] = False
    clock2.t += 19 * 3600
    assert "expired" in e2.pre_llm_call("chat-s", f"resume {p2.code}")["message"]

def test_subagent_inherits_park(repo):
    e, clock, st = make(repo)
    e.pre_tool_call("terminal", {"command": "npm ci"}, task_id="cron-s")
    e.subagent_start(parent_session_id="cron-s", child_session_id="child-s")
    st["cron"] = False   # children read None from current_cron_execution
    d = e.pre_tool_call("terminal", {"command": "git push origin main"}, task_id="child-s")
    assert d["action"] == "block" and "is parked" in d["message"]

def test_live_session_escalates(repo):
    e, clock, st = make(repo, cron=False)
    assert e.pre_tool_call("terminal", {"command": "gh pr merge 7"}, task_id="live")["action"] == "approve"
    assert e.pre_tool_call("terminal", {"command": "npm test"}, task_id="live") is None

def test_deny(repo):
    e, clock, st = make(repo); p = park_one(e)
    assert "Only the job's owner" in e.deny(p.code, "7", "telegram")
    assert "Dropped" in e.deny(p.code, "42", "telegram")
    assert e.store.get(p.code).status == "denied"
