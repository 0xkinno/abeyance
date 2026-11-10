"""The world a decision was shown, and whether it is still the same world.

A parked step is approved against a snapshot. Before it may resume, the snapshot is taken again
and compared field by field. Any difference refuses the resume with the exact change named.
Read-only, local git only (no fetch), bounded file hashing.
"""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
from pathlib import Path

from . import faults

MAX_FILES = 20
MAX_FILE_BYTES = 5 * 1024 * 1024
GIT_TIMEOUT = 5


def digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _git(cwd: str, *argv: str) -> str | None:
    try:
        out = subprocess.run(["git", "-C", cwd, *argv], capture_output=True, text=True,
                             timeout=GIT_TIMEOUT, env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"})
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def git_state(cwd: str) -> dict | None:
    if not cwd or _git(cwd, "rev-parse", "--is-inside-work-tree") != "true":
        return None
    status = _git(cwd, "status", "--porcelain=v1", "--untracked-files=normal") or ""
    return {
        "head": _git(cwd, "rev-parse", "HEAD"),
        "branch": _git(cwd, "rev-parse", "--abbrev-ref", "HEAD"),
        "upstream": _git(cwd, "rev-parse", "@{u}"),
        "status_digest": hashlib.sha256(status.encode()).hexdigest(),
        "dirty_files": len([l for l in status.splitlines() if l.strip()]),
    }


def _path_tokens(tool_name: str, args: dict) -> list[str]:
    cands: list[str] = []
    for key in ("path", "file_path", "target", "workdir"):
        if isinstance(args.get(key), str):
            cands.append(args[key])
    cmd = args.get("command")
    if isinstance(cmd, str):
        try:
            cands.extend(t for t in shlex.split(cmd) if not t.startswith("-"))
        except ValueError:
            cands.extend(cmd.split())
    return cands


def file_hashes(cwd: str, tool_name: str, args: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    base = Path(cwd or ".")
    for tok in _path_tokens(tool_name, args):
        if len(out) >= MAX_FILES:
            break
        p = Path(tok) if os.path.isabs(tok) else base / tok
        try:
            if p.is_file() and p.stat().st_size <= MAX_FILE_BYTES:
                out[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
        except OSError:
            continue
    for manifest in ("package.json", "pyproject.toml", "Cargo.toml"):
        p = base / manifest
        if p.is_file() and len(out) < MAX_FILES and str(p) not in out:
            out[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def snapshot(cwd: str, tool_name: str, args: dict) -> dict:
    faults.check("drift")
    return {
        "cwd": cwd,
        "git": git_state(cwd),
        "files": file_hashes(cwd, tool_name, args),
        "call_digest": digest({"tool": tool_name, "args": args}),
    }


def compare(before: dict, after: dict) -> list[str]:
    """Plain-words list of what changed. Empty list means the world is the one that was shown."""
    changes: list[str] = []
    if before.get("cwd") != after.get("cwd"):
        changes.append(f"working folder changed from {before.get('cwd')} to {after.get('cwd')}")
    bg, ag = before.get("git"), after.get("git")
    if bg and not ag:
        changes.append("the folder is no longer a git repository")
    elif bg and ag:
        if bg.get("branch") != ag.get("branch"):
            changes.append(f"branch changed from {bg.get('branch')} to {ag.get('branch')}")
        if bg.get("head") != ag.get("head"):
            changes.append(f"HEAD moved from {str(bg.get('head'))[:7]} to {str(ag.get('head'))[:7]}")
        if bg.get("upstream") != ag.get("upstream"):
            changes.append(f"upstream ref moved from {str(bg.get('upstream'))[:7]} to {str(ag.get('upstream'))[:7]}")
        if bg.get("status_digest") != ag.get("status_digest"):
            changes.append(f"uncommitted changes differ ({bg.get('dirty_files')} files then, {ag.get('dirty_files')} now)")
    bf, af = before.get("files") or {}, after.get("files") or {}
    for path, h in bf.items():
        if path not in af:
            changes.append(f"{path} is gone")
        elif af[path] != h:
            changes.append(f"{path} changed")
    if before.get("call_digest") != after.get("call_digest"):
        changes.append("the step itself is different from the one you were shown")
    return changes
