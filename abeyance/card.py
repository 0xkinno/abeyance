"""Every word the owner reads comes from here, never from a model. House style: no emoji, no em or en dashes."""
from __future__ import annotations

import re
import time
from datetime import datetime

from .policy import CLASSES

_BANNED = re.compile("[\u2013\u2014\U0001F300-\U0001FAFF\u2600-\u27bf]")
_MID_DASH = re.compile(r"(?<=\S) +- +(?=\S)")  # "a - b" (a dash used as a pause) reads "a, b"; list bullets stay


def clean(text: str) -> str:
    """House-style filter applied to anything shown to the owner, model text included."""
    return _MID_DASH.sub(", ", _BANNED.sub(" - ", text))


def _hhmm(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M")


def command(park) -> str:
    a = park.args
    return str(a.get("command") or a.get("path") or a.get("code", "")[:120] or park.tool)


def park_card(park, steps, *, now: float | None = None) -> str:
    now = now or time.time()
    hours = max(0, round((park.expires_at - now) / 3600))
    git = (park.snapshot or {}).get("git") or {}
    where = park.snapshot.get("cwd") or ""
    if git.get("head"):
        where += f"   branch {git.get('branch')} at {str(git['head'])[:7]}"
    lines = [
        f"Abeyance: your job \"{park.job_name}\" is waiting for you.",
        "",
        "It stopped before one step it may not take alone:",
        f"  {command(park)}",
        f"  why held: {', '.join(CLASSES.get(c, c.lower()) for c in park.classes)}",
    ]
    if where:
        lines.append(f"  where: {where}")
    if steps:
        lines += ["", "What already happened:"]
        for s in steps[-6:]:
            mark = "ok" if s["ok"] else "failed"
            lines.append(f"  {s['seq']}. {s['summary'][:60]}   {mark}")
    lines += [
        "",
        f"Reply   resume {park.code}   to finish from this step. Hermes will ask you to confirm the command itself.",
        f"Reply   /abeyance deny {park.code}   to drop it.",
        f"It expires at {_hhmm(park.expires_at)} (in {hours} h). Nothing runs until you answer.",
    ]
    return clean("\n".join(lines))


def drift_refusal(park, changes: list[str]) -> str:
    body = "\n".join(f"  - {c}" for c in changes)
    return clean(
        f"Abeyance did not resume {park.code}. The world changed since you were shown it:\n{body}\n"
        f"Nothing ran. The job runs again on its next schedule, or start it now to plan from the new state."
    )


def resume_brief(park, steps) -> str:
    done = "\n".join(f"  {s['seq']}. {s['summary']} ({'ok' if s['ok'] else 'failed'}): {s['excerpt'][:160]}" for s in steps)
    return clean(
        "[Abeyance resume, verified by code before this turn]\n"
        f"The owner approved continuing scheduled job \"{park.job_name}\" (park {park.code}).\n"
        f"Original task and progress so far:\n{done or '  (no earlier steps)'}\n"
        f"Your first action must be exactly this {park.tool} call, unchanged:\n  {command(park)}\n"
        "Hermes will ask the owner to confirm it. Do not repeat any step listed above. "
        "Then finish the remaining work of the job and report what you did."
    )
