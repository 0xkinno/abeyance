"""`hermes abeyance ...`: the terminal face of the same engine the hooks use."""
from __future__ import annotations

import json
from pathlib import Path


def setup(parser) -> None:
    sub = parser.add_subparsers(dest="abeyance_cmd")
    sub.add_parser("list", help="Steps waiting for you")
    show = sub.add_parser("show", help="The card for one waiting step")
    show.add_argument("code")
    deny = sub.add_parser("deny", help="Drop a waiting step; nothing runs")
    deny.add_argument("code")
    test = sub.add_parser("test", help="Would this command wait for you?")
    test.add_argument("command", nargs="+")
    sub.add_parser("facts", help="Measured numbers behind the README (docs/FACTS.json)")
    sub.add_parser("demo", help="Scripted run, real Abeyance code, offline, about 5 seconds")


def handle(args, get_engine) -> int:
    from . import card, list_text, test_text
    from .demo import run_demo
    cmd = getattr(args, "abeyance_cmd", None) or "list"
    if cmd == "demo":
        print(run_demo())
        return 0
    if cmd == "facts":
        print(facts_text())
        return 0
    eng = get_engine()
    if eng is None:
        print("Abeyance is not loaded. Enable it with: hermes plugins enable abeyance")
        return 1
    if cmd == "list":
        print(list_text(eng))
    elif cmd == "show":
        p = eng.store.get(args.code)
        print(card.park_card(p, eng.store.steps(p.execution_id), now=eng.env.now()) if p else "No such park.")
    elif cmd == "deny":
        print(eng.deny(args.code, "", "cli"))
    elif cmd == "test":
        print(test_text(eng, " ".join(args.command)))
    return 0


def facts_text() -> str:
    for base in (Path(__file__).resolve().parent, Path(__file__).resolve().parent.parent / "docs"):
        f = base / "FACTS.json"
        if f.is_file():
            data = json.loads(f.read_text())
            return "\n".join(f"{k}: {v}" for k, v in data.items())
    return "FACTS.json is not shipped with this install. See docs/FACTS.json in the repository."


def register_cli(ctx, get_engine) -> None:
    ctx.register_cli_command(name="abeyance", help="Cron steps waiting for you", setup_fn=setup,
                             handler_fn=lambda args: handle(args, get_engine),
                             description="List, show, drop and test the steps your scheduled runs are holding for you.")
