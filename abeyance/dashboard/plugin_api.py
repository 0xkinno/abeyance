"""Backend routes for the Desktop half and the dashboard: /api/plugins/abeyance/*.

Read the waiting steps and drop one. There is deliberately no route that runs a step: a step
runs only as the agent's own tool call in a chat, behind Hermes's approval card.
Hermes imports this file by path, so the plugin package is loaded under a private module name
and never placed on sys.path.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

_PKG_DIR = Path(__file__).resolve().parent.parent
_PKG_NAME = "hermes_plugin_abeyance_api"


def _load(module: str):
    if _PKG_NAME not in sys.modules:
        spec = importlib.util.spec_from_file_location(_PKG_NAME, _PKG_DIR / "__init__.py",
                                                      submodule_search_locations=[str(_PKG_DIR)])
        pkg = importlib.util.module_from_spec(spec)
        sys.modules[_PKG_NAME] = pkg
        spec.loader.exec_module(pkg)
    return importlib.import_module(f"{_PKG_NAME}.{module}")


_store_mod, _card, _engine = _load("store"), _load("card"), _load("engine")
_STORE: Dict[str, Any] = {}


def _announce(code: str, status: str) -> None:
    try:
        from hermes_cli.plugin_events import broadcast_plugin_event  # public plugin API
        broadcast_plugin_event("abeyance", "changed", {"code": code, "status": status})
    except Exception:
        pass


def _store():
    if "s" not in _STORE:
        _STORE["s"] = _store_mod.Store.open_default(on_change=_announce)
    return _STORE["s"]


def _park_json(p, steps=None) -> Dict[str, Any]:
    git = (p.snapshot or {}).get("git") or {}
    out = {"code": p.code, "status": p.status, "job_name": p.job_name, "command": _card.command(p),
           "classes": p.classes, "why": [_card.CLASSES.get(c, c.lower()) for c in p.classes],
           "where": (p.snapshot or {}).get("cwd"), "branch": git.get("branch"), "head": (git.get("head") or "")[:7],
           "created_at": p.created_at, "expires_at": p.expires_at, "decided_at": p.decided_at}
    if steps is not None:
        out["steps"] = [{"seq": s["seq"], "summary": s["summary"], "ok": bool(s["ok"])} for s in steps]
        out["card"] = _card.park_card(p, steps)
    return out


router = APIRouter()


@router.get("/parks")
async def list_parks(status: str = "", limit: int = 20) -> Dict[str, Any]:
    parks = _store().list_parks(status or None, limit=max(1, min(limit, 100)))
    waiting = sum(1 for p in _store().list_parks("parked", limit=100))
    return {"ok": True, "waiting": waiting, "parks": [_park_json(p) for p in parks]}


@router.get("/parks/{code}")
async def get_park(code: str) -> Dict[str, Any]:
    p = _store().get(code)
    if p is None:
        raise HTTPException(status_code=404, detail="No such park.")
    return {"ok": True, "park": _park_json(p, _store().steps(p.execution_id)),
            "events": [dict(e) for e in _store().events(code)]}


@router.post("/parks/{code}/deny")
async def deny_park(code: str) -> Dict[str, Any]:
    """The dashboard and Desktop are local to the owner, like the CLI."""
    import time
    p = _store().get(code)
    if p is None:
        raise HTTPException(status_code=404, detail="No such park.")
    dropped = _store().transition(code, "parked", "denied", decided_by="desktop", decided_at=time.time())
    return {"ok": dropped, "status": _store().get(code).status,
            "message": f"Dropped {code.upper()}. Nothing ran." if dropped else f"{code.upper()} is {p.status}."}


@router.get("/facts")
async def facts() -> Dict[str, Any]:
    for f in (_PKG_DIR / "FACTS.json", _PKG_DIR.parent / "docs" / "FACTS.json"):
        if f.is_file():
            return {"ok": True, "facts": json.loads(f.read_text())}
    return {"ok": False, "facts": {}}
