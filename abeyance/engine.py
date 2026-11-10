"""The decision logic, independent of Hermes so it can be tested with fakes.

`Engine` receives everything it needs through `Env` (clock, cron identity, session env, cwd).
`__init__.py` wires real Hermes callables into `Env`; tests wire fakes.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from . import card, drift
from .policy import CLASSES, PolicyConfig, classify
from .store import Park, Store

RESUME_RE = re.compile(r"^\s*resume\s+([A-Za-z2-9]{4})\s*[.!]?\s*$", re.I)
LOCAL_PLATFORMS = {"", "cli", "tui", "desktop", "local"}
# Text that arrives through these lanes has no authenticated person behind it, so it can never
# answer a park, whatever user id the payload claims.
NO_RESUME_PLATFORMS = {"webhook", "msgraph_webhook", "api_server", "cron"}
READ_ONLY_TOOLS = {"read_file", "search_files", "list_files", "web_search", "web_extract", "skill_view", "skills_list",
                   "session_search", "todo", "clarify"}


@dataclass
class Settings:
    expiry_hours: float = 18.0
    owners: list[str] = field(default_factory=list)       # stable platform user ids allowed to resume/deny
    interactive: str = "ask"                              # ask | off : live sessions escalate held steps to Hermes approval
    policy: PolicyConfig = field(default_factory=PolicyConfig)

    @classmethod
    def from_config(cls, get: Callable[[str, object], object]) -> "Settings":
        raw = get("owners", []) or []
        if isinstance(raw, (str, int)):          # a single id written as a scalar, not a list
            raw = [raw]
        elif not isinstance(raw, (list, tuple, set)):
            raw = []                              # unreadable owners: nobody is an owner (fails closed)
        return cls(
            expiry_hours=float(get("expiry_hours", 18.0)),
            owners=[s for s in (str(x).replace("﻿", "").strip() for x in raw) if s],
            interactive=str(get("interactive", "ask")),
            policy=PolicyConfig.from_settings({"hold": get("hold", []), "allow": get("allow", []), "workdir": get("workdir", None)}),
        )


@dataclass
class CronRun:
    job_id: str
    job_name: str
    execution_id: str
    profile: str = "default"


@dataclass
class Env:
    now: Callable[[], float] = time.time
    cron_run: Callable[[], Optional[CronRun]] = lambda: None   # ctx.current_cron_execution adapter
    session_env: Callable[[str], str] = lambda name: ""          # gateway.session_context.get_session_env
    cwd: Callable[[], str] = lambda: "."                          # agent.runtime_cwd.resolve_agent_cwd


def message_text(user_message) -> str:
    """pre_llm_call passes a list of content parts on multimodal turns; the text parts are what we read."""
    if isinstance(user_message, list):
        return " ".join(str(p.get("text", "")) for p in user_message if isinstance(p, dict) and p.get("type") == "text")
    return str(user_message or "")


def resume_code(user_message) -> Optional[str]:
    m = RESUME_RE.match(message_text(user_message))
    return m.group(1).upper() if m else None


def _summary(tool: str, args: dict) -> str:
    return str(args.get("command") or args.get("path") or args.get("query") or tool)[:120]


def _result_ok(result: str) -> tuple[bool, str]:
    try:
        data = json.loads(result)
    except (TypeError, ValueError):
        return ("error" not in str(result).lower()[:200], str(result)[:300])
    if isinstance(data, dict):
        ok = not data.get("error") and data.get("exit_code", 0) in (0, None) and data.get("success", True) is not False
        return ok, json.dumps(data)[:300]
    return True, str(data)[:300]


class Engine:
    def __init__(self, store: Store, settings: Settings, env: Env):
        self.store, self.s, self.env = store, settings, env

    # helpers
    def _run_for(self, *ids: str) -> Optional[CronRun]:
        """The cron run these ids belong to: the live cron context, or a recorded child of one.

        Hermes passes `session_id` and `task_id` to tool hooks; both are bound, so a subagent
        whose calls carry either id is still recognised as part of the unattended run."""
        ids = tuple(i for i in ids if i)
        run = self.env.cron_run()
        if run is not None:
            for i in ids:
                self.store.bind_session(i, run.execution_id, run.job_id, run.job_name, "cron")
            return run
        for i in ids:
            row = self.store.session_run(i)
            if row is not None:
                return CronRun(row["job_id"], row["job_name"], row["execution_id"])
        return None

    def is_unattended(self, *ids: str) -> bool:
        return self._run_for(*ids) is not None

    def _owner_ok(self, actor: str, platform: str) -> bool:
        if platform in NO_RESUME_PLATFORMS:
            return False
        if platform in LOCAL_PLATFORMS and not (platform == "" and actor):
            return True                           # local CLI or Desktop; an unknown platform that names a user is not local
        return bool(self.s.owners) and actor in self.s.owners

    # pre_tool_call
    def pre_tool_call(self, tool_name: str, args: dict, task_id: str = "", **kw) -> Optional[dict]:
        session_id = kw.get("session_id") or task_id or ""
        args = args if isinstance(args, dict) else {}
        run = self._run_for(session_id, task_id)
        decision = classify(tool_name, args, self.s.policy)
        call_digest = drift.digest({"tool": tool_name, "args": args})

        if run is not None:
            frozen = self.store.frozen_park(run.execution_id)
            if frozen is not None and tool_name not in READ_ONLY_TOOLS:
                return {"action": "block", "message": "ABEYANCE: this run is waiting for its owner. "
                                                      "Take no further actions. End your turn with one short sentence."}
            if not decision.hold:
                return None
            now = self.env.now()
            park = Park(code=self.store.new_code(), created_at=now, expires_at=now + self.s.expiry_hours * 3600,
                        job_id=run.job_id, job_name=run.job_name, execution_id=run.execution_id, session_id=session_id,
                        profile=run.profile, tool=tool_name, args=args, call_digest=call_digest,
                        classes=decision.classes, reasons=decision.reasons,
                        snapshot=drift.snapshot(self.env.cwd(), tool_name, args), status="parked")
            self.store.create_park(park)
            return {"action": "block", "message": f"ABEYANCE: this step needs the owner ({', '.join(decision.classes)}) and is parked. "
                                                  "Stop now: take no other actions and end your turn."}

        bound = self.store.resume_binding(session_id) if session_id else None
        if bound is not None:
            if call_digest == bound.call_digest:
                return {"action": "approve", "rule_key": f"abeyance:{bound.code}",
                        "message": card.clean(f"Abeyance {bound.code}: `{_summary(bound.tool, bound.args)}` from \"{bound.job_name}\", "
                                              f"the step you said resume to. Confirm to run it once.")}
            if decision.hold:
                return {"action": "block", "message": f"ABEYANCE: the approved step is `{_summary(bound.tool, bound.args)}`. "
                                                      "Run exactly that call first, unchanged."}
        resumed = self.store.session_park(session_id) if session_id else None
        if decision.hold and resumed is not None and self.store.was_executed(call_digest, resumed.job_id, resumed.code):
            return {"action": "block", "message": f"ABEYANCE: this exact step already ran (park {resumed.code}). Do not repeat it."}
        if decision.hold and self.s.interactive == "ask":
            why = "; ".join(CLASSES.get(c, c.lower()) for c in decision.classes)
            return {"action": "approve", "message": card.clean(f"Abeyance: `{_summary(tool_name, args)}` {why}.")}
        return None

    # post_tool_call
    def post_tool_call(self, tool_name: str, args: dict, result: str, task_id: str = "", **kw) -> None:
        session_id = kw.get("session_id") or task_id or ""
        args = args if isinstance(args, dict) else {}
        ok, excerpt = _result_ok(result)
        run = self._run_for(session_id, task_id)
        if run is not None and self.store.frozen_park(run.execution_id) is None:
            self.store.add_step(run.execution_id, tool_name, _summary(tool_name, args), ok, excerpt)
            if classify(tool_name, args, self.s.policy).hold and ok:
                self.store.mark_executed(drift.digest({"tool": tool_name, "args": args}), run.job_id, "-")
            return
        bound = self.store.resume_binding(session_id) if session_id else None
        if bound is not None and drift.digest({"tool": tool_name, "args": args}) == bound.call_digest:
            if ok:
                self.store.mark_executed(bound.call_digest, bound.job_id, bound.code)
                self.store.transition(bound.code, "resumed", "executed", executed_at=self.env.now(), result_excerpt=excerpt)
            else:
                self.store.event(bound.code, "step_failed", excerpt)

    # transform_llm_output
    def transform_llm_output(self, response_text: str, session_id: str = "", **kw) -> Optional[str]:
        run = self._run_for(session_id)
        if run is None:
            return None
        park = self.store.frozen_park(run.execution_id)
        if park is None or park.status != "parked":
            return None
        return card.park_card(park, self.store.steps(run.execution_id), now=self.env.now())

    # pre_llm_call
    def pre_llm_call(self, session_id: str = "", user_message="", **kw) -> Optional[dict]:
        code = resume_code(user_message)
        if code is None:
            return None
        actor = self.env.session_env("HERMES_SESSION_ACTOR_ID")
        platform = self.env.session_env("HERMES_SESSION_PLATFORM") or kw.get("platform", "")
        if self.is_unattended(session_id) or not self._owner_ok(actor, platform):
            self.store.event(code, "refused_actor", f"{platform}:{actor}")
            return {"action": "block", "message": "Abeyance: only the job's owner can resume it. Nothing ran."}
        park = self.store.get(code)
        if park is None:
            return {"action": "block", "message": f"Abeyance has no park named {code}."}
        if park.status != "parked":
            return {"action": "block", "message": f"Abeyance: {code} is already {park.status}."}
        if self.env.now() > park.expires_at:
            self.store.transition(code, "parked", "expired")
            return {"action": "block", "message": f"Abeyance: {code} expired. Nothing ran."}
        changes = drift.compare(park.snapshot, drift.snapshot(park.snapshot.get("cwd") or self.env.cwd(), park.tool, park.args))
        if changes:
            self.store.transition(code, "parked", "drifted", decided_by=actor or platform, decided_at=self.env.now())
            return {"action": "block", "message": card.drift_refusal(park, changes)}
        if not self.store.transition(code, "parked", "resumed", decided_by=actor or platform,
                                     decided_at=self.env.now(), resume_session=session_id):
            return {"action": "block", "message": f"Abeyance: {code} was already answered."}
        return {"context": card.resume_brief(park, self.store.steps(park.execution_id))}

    # subagent_start
    def subagent_start(self, parent_session_id: str | None = None, child_session_id: str | None = None,
                       child_subagent_id: str | None = None, **kw) -> None:
        """Children of a cron run read None from current_cron_execution(), so bind their ids to the run."""
        row = self.store.session_run(parent_session_id) if parent_session_id else None
        run = self.env.cron_run()
        target = (row["execution_id"], row["job_id"], row["job_name"]) if row is not None else \
            ((run.execution_id, run.job_id, run.job_name) if run is not None else None)
        if target is None:
            return
        for child in (child_session_id, child_subagent_id):
            if child:
                self.store.bind_session(child, *target, "child")

    # /abeyance deny
    def deny(self, code: str, actor: str, platform: str) -> str:
        if not self._owner_ok(actor, platform):
            return "Only the job's owner can answer this."
        if self.store.transition(code, "parked", "denied", decided_by=actor or platform, decided_at=self.env.now()):
            return f"Dropped {code.upper()}. Nothing ran."
        p = self.store.get(code)
        return f"{code.upper()} is {p.status if p else 'unknown'}."
