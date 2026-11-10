"""Both directions on the pre-registered corpora: held rate on world.txt, false holds on everyday.txt.

Usage: python eval/corpora.py   (writes eval/results/corpora.json; pure, executes nothing)
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from abeyance.policy import classify  # noqa: E402


def run(name):
    rows = []
    for n, line in enumerate((ROOT / "eval" / f"{name}.txt").read_text().splitlines(), 1):
        if not line.strip():
            continue
        d = classify("terminal", {"command": line})
        rows.append({"line": n, "command": line, "held": d.hold, "classes": d.classes, "reasons": d.reasons})
    return rows


world, everyday = run("world"), run("everyday")
out = {
    "world_total": len(world), "world_held": sum(r["held"] for r in world),
    "world_missed": [r for r in world if not r["held"]],
    "everyday_total": len(everyday), "everyday_false_holds": sum(r["held"] for r in everyday),
    "everyday_held": [r for r in everyday if r["held"]],
    "world": world, "everyday": everyday,
}
(ROOT / "eval" / "results").mkdir(parents=True, exist_ok=True)
(ROOT / "eval" / "results" / "corpora.json").write_text(json.dumps(out, indent=1) + "\n")
print(f"world held {out['world_held']}/{out['world_total']}; everyday false holds {out['everyday_false_holds']}/{out['everyday_total']}")
for r in out["world_missed"]:
    print("  MISSED  ", r["line"], r["command"])
for r in out["everyday_held"]:
    print("  HELD    ", r["line"], r["command"], r["classes"])
