"""Regressions found by the red team round on 2026-11-10: each case held something it should have held,
or let someone through who should not have been let through."""
import pytest

from abeyance.engine import Engine, Env, Settings, CronRun
from abeyance.policy import PolicyConfig, classify
from abeyance.store import Store


@pytest.mark.parametrize("command", [
    "git -C . push", "git -c a=b push origin main", "bash -lc 'git push'", "sudo -u root git push",
    "nice -n 10 git push", "echo a\ngit push", "gh api repos/x/y/issues -f title=t",
    "gh api --method=POST repos/x/y/issues", "npm -r publish", "pnpm -r publish",
    "python -m twine upload dist/*", "npx vercel --prod",
])
def test_disguised_world_steps_are_held(command):
    assert classify("terminal", {"command": command}).hold


@pytest.mark.parametrize("command", ["git status", "git log --oneline", "gh api repos/x/y", "ls -la", "npm test", "git diff"])
def test_everyday_steps_are_not_held(command):
    assert not classify("terminal", {"command": command}).hold


@pytest.mark.parametrize("tool,hold", [
    ("mcp__x__update_record", True), ("mcp__x__send_status", True), ("mcp__x__get_and_delete", True),
    ("mcp__x__createIssue", True), ("mcp__x__list_issues", False), ("mcp__x__search_messages", False),
    ("mcp__x__getStatus", False),
])
def test_tool_names_are_read_word_by_word(tool, hold):
    assert classify(tool, {}).hold is hold


def test_urllib_write_in_code_is_held():
    code = "import urllib.request\nurllib.request.urlopen('http://a.com', data=b'x')"
    assert classify("execute_code", {"code": code}).hold


def test_path_traversal_out_of_workdir_is_held():
    cfg = PolicyConfig(workdir="/work")
    assert classify("write_file", {"path": "/work/../etc/x"}, cfg).hold
    assert not classify("write_file", {"path": "/work/src/x"}, cfg).hold


def _engine(tmp_path, owners=("42",), platform="telegram", actor="42", cron=False):
    state = {"cron": cron, "actor": actor, "platform": platform, "exec": "exec1"}
    env = Env(now=lambda: 1000.0,
              cron_run=lambda: CronRun("job1", "Nightly", state["exec"]) if state["cron"] else None,
              session_env=lambda n: {"HERMES_SESSION_ACTOR_ID": state["actor"], "HERMES_SESSION_PLATFORM": state["platform"]}.get(n, ""),
              cwd=lambda: str(tmp_path))
    return Engine(Store(tmp_path / "t.db"), Settings(owners=list(owners)), env), state


def test_scalar_and_broken_owners_fail_closed():
    assert Settings.from_config(lambda k, d: {"owners": "12345"}.get(k, d)).owners == ["12345"]
    assert Settings.from_config(lambda k, d: {"owners": 12345}.get(k, d)).owners == ["12345"]
    assert Settings.from_config(lambda k, d: {"owners": {"a": 1}}.get(k, d)).owners == []


def test_unknown_platform_naming_a_user_is_not_local(tmp_path):
    eng, state = _engine(tmp_path, platform="", actor="999")
    assert not eng._owner_ok("999", "")
    assert eng._owner_ok("", "")


def test_a_frozen_run_cannot_write_memory(tmp_path):
    eng, state = _engine(tmp_path, cron=True)
    eng.pre_tool_call("terminal", {"command": "git push origin main"}, session_id="s1")
    out = eng.pre_tool_call("memory", {"action": "add"}, session_id="s1")
    assert out and out["action"] == "block"


def test_cron_session_cannot_resume_its_own_park(tmp_path):
    eng, state = _engine(tmp_path, cron=True)
    eng.pre_tool_call("terminal", {"command": "git push origin main"}, session_id="s1")
    code = eng.store.frozen_park("exec1").code
    out = eng.pre_llm_call(session_id="s1", user_message=f"resume {code}")
    assert out and out["action"] == "block"
    assert eng.store.get(code).status == "parked"


def test_a_stranger_learns_nothing_about_which_codes_exist(tmp_path):
    eng, state = _engine(tmp_path, platform="telegram", actor="7")
    out = eng.pre_llm_call(session_id="chat", user_message="resume ZZZZ")
    assert "only the job's owner" in out["message"]


def test_the_same_command_on_a_later_night_parks_again(tmp_path):
    eng, state = _engine(tmp_path, cron=True)
    args = {"command": "npm publish"}
    eng.pre_tool_call("terminal", args, session_id="s1")
    code = eng.store.frozen_park("exec1").code
    eng.store.mark_executed(__import__("abeyance.drift", fromlist=["digest"]).digest({"tool": "terminal", "args": args}), "job1", code)
    eng.store.conn.execute("UPDATE parks SET status='executed' WHERE code=?", (code,))
    eng.store.conn.commit()
    state["exec"] = "exec2"                      # the next night is a new execution
    out = eng.pre_tool_call("terminal", args, session_id="s2")
    assert out and "needs the owner" in out["message"]


def test_non_dict_args_do_not_crash_a_cron_run(tmp_path):
    eng, state = _engine(tmp_path, cron=True)
    assert eng.pre_tool_call("terminal", "not a dict", session_id="s1") is None
