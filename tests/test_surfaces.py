import importlib.util
import json
import sys
import threading
import types
from pathlib import Path

import pytest

import abeyance
from abeyance import cli, demo, faults
from abeyance.engine import Engine, Env, Settings, CronRun, resume_code
from abeyance.store import Store
from test_engine import make, park_one, repo  # noqa: F401  (fixture reuse)

ROOT = Path(__file__).resolve().parents[1]


def test_demo_shows_three_outcomes_offline():
    out = demo.run_demo()
    assert "scripted run, real Abeyance code" in out
    assert "approve: Abeyance" in out and "`npm publish`" in out
    assert "HEAD moved from" in out and "Nothing ran" in out
    assert "only the job's owner can resume it" in out and "is still parked" in out


def test_resume_code_reads_text_and_multimodal_parts():
    assert resume_code("resume k7q2") == "K7Q2"
    assert resume_code("Resume K7Q2.") == "K7Q2"
    assert resume_code([{"type": "image_url"}, {"type": "text", "text": "resume K7Q2"}]) == "K7Q2"
    assert resume_code("please resume K7Q2 now") is None


@pytest.mark.parametrize("platform", ["webhook", "msgraph_webhook", "api_server"])
def test_unauthenticated_lanes_can_never_resume(repo, platform):
    e, clock, state = make(repo, owners=("42",))
    park_one(e)
    state.update(cron=False, platform=platform, actor="42")
    code = e.store.list_parks("parked")[0].code
    d = e.pre_llm_call("live", f"resume {code}")
    assert d["action"] == "block" and e.store.get(code).status == "parked"


def test_every_transition_is_announced(repo):
    seen = []
    e, clock, state = make(repo)
    e.store.on_change = lambda code, status: seen.append(status)
    park_one(e)
    state["cron"] = False
    code = e.store.list_parks("parked")[0].code
    e.pre_llm_call("live", f"resume {code}")
    e.post_tool_call("terminal", {"command": "npm publish"}, '{"exit_code":0}', session_id="live")
    assert seen == ["parked", "resumed", "executed"]


def test_compare_and_set_gives_one_winner_across_threads(tmp_path):
    s = Store(tmp_path / "a.db")
    from abeyance.store import Park
    s.create_park(Park("ABCD", 0, 9e9, "j", "J", "x", "s", "p", "terminal", {}, "d", [], [], {}, "parked"))
    wins = []
    barrier = threading.Barrier(8)

    def go(i):
        other = Store(tmp_path / "a.db")
        barrier.wait()
        if other.transition("ABCD", "parked", "resumed", resume_session=f"s{i}"):
            wins.append(i)
    ts = [threading.Thread(target=go, args=(i,)) for i in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(wins) == 1


@pytest.mark.parametrize("kind", ["store", "policy", "drift"])
def test_fault_switch_raises_only_when_set(monkeypatch, kind):
    faults.check(kind)
    monkeypatch.setenv("ABEYANCE_FAULT", kind)
    with pytest.raises(faults.InjectedFault):
        faults.check(kind)


class FakeCtx:
    def __init__(self):
        self.hooks, self.commands, self.cli, self.blueprints, self.skills, self.emitted = {}, {}, {}, {}, {}, []
        self.choice = "drop"

    def get_config(self, key, default=None):
        return {"owners": ["42"]}.get(key, default)

    def current_cron_execution(self):
        return None

    def register_hook(self, name, cb, **kw):
        self.hooks[name] = cb

    def register_command(self, name, handler, **kw):
        self.commands[name] = handler

    def register_cli_command(self, name, help, setup_fn, handler_fn=None, description=""):
        self.cli[name] = (setup_fn, handler_fn)

    def register_skill(self, name, path, description=""):
        self.skills[name] = path

    def register_automation_blueprint(self, key, **kw):
        self.blueprints[key] = kw

    def ask_choice(self, question, choices):
        return self.choice

    def emit(self, event, payload=None):
        self.emitted.append((event, payload))


@pytest.fixture
def registered(monkeypatch, tmp_path):
    monkeypatch.setattr(Store, "open_default", classmethod(lambda cls, on_change=None: cls(tmp_path / "p.db", on_change=on_change)))
    ctx = FakeCtx()
    abeyance.register(ctx)
    return ctx


def test_register_wires_every_surface(registered):
    ctx = registered
    assert set(ctx.hooks) == {"pre_tool_call", "post_tool_call", "transform_llm_output", "pre_llm_call", "subagent_start"}
    assert "abeyance" in ctx.commands and "abeyance" in ctx.cli and "abeyance" in ctx.skills
    bp = ctx.blueprints["nightly-release"]
    assert bp["title"] == "Nightly release that waits for you" and "{publish}" in bp["prompt_template"]
    manifest = (ROOT / "abeyance" / "plugin.yaml").read_text()
    for hook in ctx.hooks:
        assert hook in manifest


def test_slash_test_list_and_deny_with_confirmation(registered, repo):
    ctx = registered
    slash = ctx.commands["abeyance"]
    assert slash("").startswith("Nothing is waiting")
    assert slash("test npm publish").startswith("HELD: PUBLISH")
    assert slash("test git status").startswith("allowed")
    e = abeyance._ENGINE
    e.env = Env(now=lambda: 1.0, cron_run=lambda: CronRun("j", "Nightly release", "ex"), cwd=lambda: str(repo))
    e.pre_tool_call("terminal", {"command": "npm publish"}, task_id="c")
    code = e.store.list_parks("parked")[0].code
    assert code in slash("list")
    ctx.choice = "keep"
    assert "still waiting" in slash(f"deny {code}", platform="cli")
    ctx.choice = "drop"
    assert slash(f"deny {code}", platform="telegram", source=types.SimpleNamespace(user_id="7")) == "Only the job's owner can answer this."
    assert slash(f"deny {code}", platform="cli") == f"Dropped {code}. Nothing ran."
    assert ("changed", {"code": code, "status": "denied"}) in ctx.emitted


def test_resume_hook_fails_closed_on_internal_error(registered, monkeypatch):
    hook = registered.hooks["pre_llm_call"]
    monkeypatch.setattr(abeyance._ENGINE.store, "get", lambda code: (_ for _ in ()).throw(RuntimeError("db gone")))
    d = hook(session_id="s", user_message="resume K7Q2")
    assert d["action"] == "block" and "Nothing ran" in d["message"]
    assert hook(session_id="s", user_message="hello") is None


def test_tool_hook_fails_closed_in_cron_and_open_in_chat(registered, monkeypatch):
    hook = registered.hooks["pre_tool_call"]
    monkeypatch.setenv("ABEYANCE_FAULT", "policy")
    assert hook(tool_name="terminal", args={"command": "npm publish"}, task_id="live") is None
    abeyance._ENGINE.env.cron_run = lambda: CronRun("j", "J", "ex")
    d = hook(tool_name="terminal", args={"command": "npm test"}, task_id="cron")
    assert d["action"] == "block" and "held, not run" in d["message"]


def test_cli_parser_and_handlers(registered, capsys):
    import argparse
    setup, handler = registered.cli["abeyance"]
    p = argparse.ArgumentParser()
    setup(p)
    assert handler(p.parse_args(["test", "gh", "pr", "merge", "4"])) == 0
    assert "HELD: MERGE" in capsys.readouterr().out
    assert handler(p.parse_args(["list"])) == 0
    assert handler(p.parse_args(["facts"])) == 0


def test_dashboard_api_has_no_route_that_runs_a_step():
    src = (ROOT / "abeyance" / "dashboard" / "plugin_api.py").read_text()
    routes = [l for l in src.splitlines() if l.strip().startswith("@router.")]
    assert routes == ['@router.get("/parks")', '@router.get("/parks/{code}")',
                      '@router.post("/parks/{code}/deny")', '@router.get("/facts")']


def test_desktop_half_imports_only_the_sdk():
    src = (ROOT / "abeyance" / "desktop" / "plugin.js").read_text()
    imports = {l.split("from")[-1].strip().strip("'\"") for l in src.splitlines() if l.startswith("import ")}
    assert imports <= {"@hermes/plugin-sdk", "react", "react/jsx-runtime"}
    assert "host.composer.submit" in src and "plugin.abeyance.changed" in src


def test_owner_ids_ignore_byte_order_mark_and_spaces():
    from abeyance.engine import Settings
    s = Settings.from_config(lambda k, d: {"owners": ["﻿1676349577", " 42 ", ""]}.get(k, d))
    assert s.owners == ["1676349577", "42"]
