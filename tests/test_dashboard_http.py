"""Calls the dashboard routes through FastAPI's test client. Needs Hermes and fastapi importable
(HERMES_SRC on sys.path, HERMES_HOME set); skipped otherwise, so plain CI stays dependency-free."""
import importlib.util
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
src = os.environ.get("HERMES_SRC")
if not src:
    pytest.skip("HERMES_SRC not set", allow_module_level=True)
sys.path.insert(0, src)
pytest.importorskip("plugins.plugin_storage")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_engine import make, park_one, repo  # noqa: F401

API = Path(__file__).resolve().parents[1] / "abeyance" / "dashboard" / "plugin_api.py"


def test_routes_list_show_deny_and_facts(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    spec = importlib.util.spec_from_file_location("abeyance_dash_test", API)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # Park through an engine that shares the route's store.
    e, clock, state = make(repo)
    e.store = mod._store()
    park_one(e)
    code = e.store.list_parks("parked")[0].code
    app = FastAPI()
    app.include_router(mod.router, prefix="/api/plugins/abeyance")
    c = TestClient(app)
    r = c.get("/api/plugins/abeyance/parks").json()
    assert r["waiting"] == 1 and r["parks"][0]["command"] == "npm publish"
    d = c.get(f"/api/plugins/abeyance/parks/{code}").json()
    assert d["park"]["steps"][0]["summary"] == "npm ci" and "resume " + code in d["park"]["card"]
    assert c.get("/api/plugins/abeyance/parks/ZZZZ").status_code == 404
    assert c.post(f"/api/plugins/abeyance/parks/{code}/deny").json()["ok"] is True
    assert c.post(f"/api/plugins/abeyance/parks/{code}/deny").json()["ok"] is False
    assert c.get("/api/plugins/abeyance/parks?status=parked").json()["waiting"] == 0
    assert "facts" in c.get("/api/plugins/abeyance/facts").json()
