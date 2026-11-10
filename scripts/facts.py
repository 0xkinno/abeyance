"""Build docs/FACTS.json from real run results. Every headline number in the docs comes from here.

Usage: python scripts/facts.py          (write)
       python scripts/facts.py --check  (CI: fail if the committed file differs from a rebuild)
Inputs: eval/results/*.json, docs/detector_probe_*.json, eval/results/real_run.json (if present).
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
RES = ROOT / "eval" / "results"


def load(p):
    return json.loads(p.read_text()) if p.exists() else {}


def build():
    probe_files = sorted((ROOT / "docs").glob("detector_probe_*.json"))
    probe = load(probe_files[-1]) if probe_files else {}
    corpora, prereg = load(RES / "corpora.json"), load(RES / "corpora_prereg_2026-11-10.json")
    campaign, real, tests = load(RES / "campaign.json"), load(RES / "real_run.json"), load(RES / "tests.json")
    cases = campaign.get("cases", [])
    breaks = [c for c in cases if c["category"] not in ("counterfactual", "cost", "real loop")]

    def ev(name):
        return next((c["evidence"] for c in cases if c["case"] == name), {})
    drift_calls = [c["evidence"].get("model_calls") for c in cases if c["category"] == "drift"]
    return {
        "hermes_commit": campaign.get("hermes_commit") or probe.get("hermes_commit"),
        "detector_machine_flagged": probe.get("machine_flagged"), "detector_machine_total": probe.get("machine_total"),
        "detector_world_flagged": probe.get("world_flagged"), "detector_world_total": probe.get("world_total"),
        "detector_everyday_flagged": probe.get("everyday_flagged"), "detector_everyday_total": probe.get("everyday_total"),
        "abeyance_world_held_preregistered": prereg.get("world_held"),
        "abeyance_world_held": corpora.get("world_held"), "abeyance_world_total": corpora.get("world_total"),
        "abeyance_everyday_false_holds": corpora.get("everyday_false_holds"),
        "abeyance_everyday_total": corpora.get("everyday_total"),
        "abeyance_everyday_false_hold_lines": [r["line"] for r in corpora.get("everyday_held", [])],
        "real_loop_cases_total": len(cases), "real_loop_cases_passed": sum(c["passed"] for c in cases),
        "break_cases_total": len(breaks), "break_cases_blocked": sum(c["passed"] for c in breaks),
        "model_calls_added_per_park": ev("model_calls_added_by_a_park").get("added"),
        "model_calls_per_drift_refusal": max(drift_calls) if drift_calls and None not in drift_calls else None,
        "real_run_release_url": real.get("release_url"),
        "real_run_at": real.get("at"),
        "tests_passed": tests.get("passed"),
        "campaign_generated_at": campaign.get("generated_at"),
    }


def main():
    facts = build()
    text = json.dumps(facts, indent=1) + "\n"
    dest = ROOT / "docs" / "FACTS.json"
    if "--check" in sys.argv:
        if not dest.exists() or dest.read_text() != text:
            print("docs/FACTS.json is stale: run python scripts/facts.py and commit it")
            sys.exit(1)
        print("FACTS ok")
        return
    dest.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
