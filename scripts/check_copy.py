"""House style: no em or en dashes and no emoji in shipped text (README, docs, plugin copy)."""
import pathlib, re, sys
BAD = re.compile("[–—\U0001F300-\U0001FAFF☀-➿]")
root = pathlib.Path(__file__).resolve().parents[1]
files = [p for p in root.rglob("*") if p.suffix in {".md", ".py", ".yaml", ".js"} and "reference" not in p.parts and ".git" not in p.parts]
bad = [(p, i + 1) for p in files for i, l in enumerate(p.read_text(errors="ignore").splitlines()) if BAD.search(l) and p.name != "check_copy.py"]
for p, n in bad:
    print(f"{p.relative_to(root)}:{n}")
sys.exit(1 if bad else 0)
