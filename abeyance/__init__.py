"""Abeyance: a Hermes cron run that waits for you at the one step it should not take alone.

Registration only. Logic lives in engine.py (pure, tested with fakes).
Every callback fails safe: inside a cron run an internal error BLOCKS the step (it cannot
silently run unasked); in live sessions an internal error leaves Hermes's own behaviour unchanged.
A resume turn whose check fails internally is refused, never waved through.
"""
from __future__ import annotations

import logging
from pathlib import Path

from . import card
from .engine import CronRun, Engine, Env, Settings, resume_code
from .policy import CLASSES, classify
from .store import Store

logger = logging.getLogger(__name__)
_ENGINE: Engine | None = None
_CTX = None
PLUGIN_ID = "abeyance"


def _env(ctx) -> Env:
    def cron_run():
        try:
            ex = ctx.current_cron_execution()
        except Exception:
            return None
        return CronRun(ex.job_id, ex.job_name, ex.execution_id, getattr(ex, "profile", "default")) if ex else None

    def session_env(name: str) -> str:
        try:
            from gateway.session_context import get_session_env  # public plugin API
            return get_session_env(name) or ""
        except Exception:
            return ""

    def cwd() -> str:
        try:
            from agent.runtime_cwd import resolve_agent_cwd  # public plugin API
            return str(resolve_agent_cwd())
        except Exception:
            return str(Path.cwd())

    return Env(cron_run=cron_run, session_env=session_env, cwd=cwd)


def _announce(code: str, status: str) -> None:
    """Every park transition reaches the Desktop half and in-process subscribers."""
    payload = {"code": code, "status": status}
    try:
        from hermes_cli.plugin_events import broadcast_plugin_event  # public plugin API
        broadcast_plugin_event(PLUGIN_ID, "changed", payload)
    except Exception:
        logger.debug("abeyance: desktop broadcast unavailable", exc_info=True)
    if _CTX is not None:
        try:
            _CTX.emit("changed", payload)
        except Exception:
            logger.debug("abeyance: ctx.emit failed", exc_info=True)


def _guarded(name: str, fn, *, in_cron_fail_closed: bool = False):
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            logger.exception("abeyance %s failed", name)
            if in_cron_fail_closed and _unattended(kwargs):
                return {"action": "block", "message": "ABEYANCE: internal error; this step was held, not run."}
            return None
    return wrapper


def _unattended(kwargs: dict) -> bool:
    eng = _ENGINE
    if eng is None:
        return False
    try:
        return eng.is_unattended(kwargs.get("session_id") or "", kwargs.get("task_id") or "")
    except Exception:  # the store itself is broken: trust only Hermes's own cron identity
        try:
            return eng.env.cron_run() is not None
        except Exception:
            return True


def _guarded_resume(fn):
    """pre_llm_call: a raising hook is skipped by Hermes and the turn goes ahead, so a resume
    message whose checks fail internally is refused here instead."""
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            logger.exception("abeyance pre_llm_call failed")
            if resume_code(kwargs.get("user_message", args[1] if len(args) > 1 else "")):
                return {"action": "block", "message": "Abeyance could not check this resume (internal error). Nothing ran."}
            return None
    return wrapper


USAGE = "Usage: /abeyance [list | show CODE | deny CODE | test COMMAND | policy | demo]"


def _slash(raw_args: str, *, session_id: str = "", platform: str = "", source=None, **_):
    eng = _ENGINE
    if eng is None:
        return "Abeyance is not loaded."
    parts = (raw_args or "").split()
    sub = parts[0].lower() if parts else "list"
    actor = str(getattr(source, "user_id", "") or "")
    if sub == "list":
        return list_text(eng)
    if sub == "show" and len(parts) > 1:
        p = eng.store.get(parts[1])
        return card.park_card(p, eng.store.steps(p.execution_id), now=eng.env.now()) if p else "No such park."
    if sub == "deny" and len(parts) > 1:
        code = parts[1].upper()
        p = eng.store.get(code)
        if p is None:
            return "No such park."
        if p.status == "parked" and _CTX is not None:
            try:
                choice = _CTX.ask_choice(f"Drop {code}? `{card.command(p)}` will not run.",
                                         [{"value": "drop", "label": "Drop it"}, {"value": "keep", "label": "Keep waiting"}])
            except Exception:
                choice = None
            if choice == "keep":
                return f"{code} is still waiting."
        return eng.deny(code, actor, platform)
    if sub == "test" and len(parts) > 1:
        return test_text(eng, " ".join(parts[1:]))
    if sub == "policy":
        return "\n".join(f"{k}: {v}" for k, v in CLASSES.items())
    if sub == "demo":
        from .demo import run_demo
        return run_demo()
    return USAGE


def list_text(eng: Engine) -> str:
    parks = eng.store.list_parks("parked")
    if not parks:
        return "Nothing is waiting for you."
    return "\n".join(f"{p.code}  {p.job_name}  {card.command(p)[:60]}  ({', '.join(p.classes)})" for p in parks)


def test_text(eng: Engine, command: str) -> str:
    d = classify("terminal", {"command": command}, eng.s.policy)
    return card.clean(f"{'HELD' if d.hold else 'allowed'}: {d.label()}  {'; '.join(d.reasons)}")


def register(ctx):
    global _ENGINE, _CTX
    _CTX = ctx
    settings = Settings.from_config(lambda k, d: ctx.get_config(k, default=d))
    _ENGINE = Engine(Store.open_default(on_change=_announce), settings, _env(ctx))
    e = _ENGINE
    ctx.register_hook("pre_tool_call", _guarded("pre_tool_call", e.pre_tool_call, in_cron_fail_closed=True))
    ctx.register_hook("post_tool_call", _guarded("post_tool_call", e.post_tool_call))
    ctx.register_hook("transform_llm_output", _guarded("transform_llm_output", e.transform_llm_output))
    ctx.register_hook("pre_llm_call", _guarded_resume(e.pre_llm_call))
    ctx.register_hook("subagent_start", _guarded("subagent_start", e.subagent_start))
    ctx.register_command("abeyance", _slash, description="Cron steps waiting for you",
                         args_hint="[list|show|deny|test|policy|demo]")
    from .cli import register_cli
    register_cli(ctx, lambda: _ENGINE)
    skill = Path(__file__).parent / "skills" / "abeyance" / "SKILL.md"
    if skill.exists():
        ctx.register_skill("abeyance", skill, description="Write scheduled jobs that park well at the step that needs you.")
    ctx.register_automation_blueprint(
        "nightly-release", title="Nightly release that waits for you",
        description="Update, test and version a repo at night; Abeyance holds the publish step until you say yes.",
        category="work", schedule_template="{minute} {hour} * * *",
        prompt_template=("In {repo}: update dependencies, run `{test}`, and if it passes bump the patch version. "
                         "Last, run `{publish}`. Report what you did."),
        slots=[{"name": "repo", "type": "text", "label": "Repo folder", "default": "~/code/app"},
               {"name": "test", "type": "text", "label": "Test command", "default": "npm test"},
               {"name": "publish", "type": "text", "label": "Publish command", "default": "npm publish"},
               {"name": "time", "type": "time", "label": "What time?", "default": "02:00"},
               {"name": "deliver", "type": "enum", "label": "Where to reach you?", "default": "origin",
                "options": ["origin", "local"], "strict": False}],
        skills=["abeyance:abeyance"], tags=["release", "night"])
