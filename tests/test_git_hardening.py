"""Host-side git must not run anything the job's folder configures (maintainer review of ef7c6c1)."""
import os
import subprocess
import sys

from abeyance import drift


def _git(cwd, *a):
    subprocess.run(["git", "-C", str(cwd), *a], check=True, capture_output=True)


def _repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "a.txt").write_text("a")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "one")
    return tmp_path


def test_git_gets_a_minimal_environment(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-secret")
    monkeypatch.setenv("GH_TOKEN", "ghp_secret")
    env = drift._git_env()
    assert "OPENROUTER_API_KEY" not in env and "GH_TOKEN" not in env
    assert env["GIT_TERMINAL_PROMPT"] == "0" and env["GIT_OPTIONAL_LOCKS"] == "0"
    assert env["GIT_CONFIG_NOSYSTEM"] == "1" and env["GIT_CONFIG_GLOBAL"] == os.devnull


def test_git_is_called_with_helpers_off_and_no_stdin(monkeypatch, tmp_path):
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"], seen["kw"] = cmd, kw
        return subprocess.CompletedProcess(cmd, 0, stdout="true\n", stderr="")

    monkeypatch.setattr(drift.subprocess, "run", fake_run)
    drift._git(str(tmp_path), "rev-parse", "--is-inside-work-tree")
    assert "core.fsmonitor=false" in seen["cmd"] and f"core.hooksPath={os.devnull}" in seen["cmd"]
    assert seen["kw"]["stdin"] == subprocess.DEVNULL and "env" in seen["kw"]


def test_a_repo_configured_fsmonitor_does_not_run(tmp_path):
    repo = _repo(tmp_path)
    marker = repo / "ran.txt"
    hook = repo / "hook.py"
    hook.write_text(f"open(r'{marker}', 'w').write('x')\n")
    _git(repo, "config", "core.fsmonitor", f'"{sys.executable}" "{hook}"')
    state = drift.git_state(str(repo))
    assert state and state["head"]
    assert not marker.exists()


def test_status_is_skipped_when_the_repo_defines_filter_drivers(tmp_path):
    repo = _repo(tmp_path)
    _git(repo, "config", "filter.evil.clean", "cat")
    state = drift.git_state(str(repo))
    assert state["status_skipped"] is True and state["dirty_files"] == 0 and state["head"]
    (repo / "b.txt").write_text("b")                 # an uncommitted file is not seen when status is skipped
    assert drift.git_state(str(repo))["dirty_files"] == 0


def test_normal_repo_still_reports_uncommitted_changes(tmp_path):
    repo = _repo(tmp_path)
    (repo / "b.txt").write_text("b")
    state = drift.git_state(str(repo))
    assert state["status_skipped"] is False and state["dirty_files"] == 1
