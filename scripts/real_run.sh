#!/usr/bin/env bash
# Real run helper for Codespaces (docs/CODESPACES.md). Reads secrets from the environment only.
set -euo pipefail
HH="${HERMES_HOME:-$HOME/.hermes}"
DEMO="$HOME/abeyance-demo"
cmd="${1:-help}"

need() { for v in "$@"; do [ -n "${!v:-}" ] || { echo "missing secret: $v"; exit 1; }; done; }

case "$cmd" in
configure)
  need TELEGRAM_BOT_TOKEN TELEGRAM_OWNER_ID OPENROUTER_API_KEY
  mkdir -p "$HH"
  touch "$HH/.env" && chmod 600 "$HH/.env"
  grep -v -E '^(TELEGRAM_BOT_TOKEN|TELEGRAM_ALLOWED_USERS|OPENROUTER_API_KEY)=' "$HH/.env" > "$HH/.env.tmp" || true
  { cat "$HH/.env.tmp"; echo "TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN"; echo "TELEGRAM_ALLOWED_USERS=$TELEGRAM_OWNER_ID";
    echo "OPENROUTER_API_KEY=$OPENROUTER_API_KEY"; } > "$HH/.env"; rm -f "$HH/.env.tmp"
  hermes config set model.provider openrouter
  hermes config set model.default "${HERMES_MODEL:-anthropic/claude-sonnet-4.6}"
  hermes config set plugins.entries.abeyance.settings.owners "[\"$TELEGRAM_OWNER_ID\"]"
  hermes plugins enable abeyance
  hermes gateway restart || hermes gateway start
  hermes plugins validate "$(pwd)/abeyance" --install-deps | tee eval/results/validate_live.txt
  hermes plugins doctor "$(pwd)/abeyance" --ci | tee eval/results/doctor_live.txt
  ;;
probe)
  { echo "# live probe $(date -u +%FT%TZ)"; hermes --version; hermes plugins list | grep -i abeyance || true;
    hermes abeyance test git push origin main; hermes abeyance list; } | tee eval/results/live_probe.txt
  ;;
night)
  need DEMO_GH_TOKEN
  [ -d "$DEMO" ] || GH_TOKEN="$DEMO_GH_TOKEN" gh repo clone 0xkinno/abeyance-demo "$DEMO"
  git -C "$DEMO" config user.name 0xkinno
  git -C "$DEMO" config user.email "${DEMO_EMAIL:-0xkinno@users.noreply.github.com}"
  # The job runs inside the gateway, which does not have DEMO_GH_TOKEN in its environment, and the
  # Codespace's own helper only covers this repo. Clear the chain and bake the token in at config time.
  git -C "$DEMO" config --replace-all credential.helper ''
  git -C "$DEMO" config --add credential.helper "!f() { echo username=x-access-token; echo password=$DEMO_GH_TOKEN; }; f"
  hermes cron create "1d" "In this repo: run npm test. If it passes, bump the patch version with npm version patch, then run git push origin main --follow-tags, then gh release create v\$(node -p \"require('./package.json').version\") --generate-notes. Report what you did." \
    --name "Nightly release (demo)" --deliver telegram --workdir "$DEMO" | tee /tmp/abeyance-cron.txt
  id=$(grep -o 'Created job: [^ ]*' /tmp/abeyance-cron.txt | awk '{print $3}')
  GH_TOKEN="$DEMO_GH_TOKEN" hermes cron run "$id"
  hermes abeyance list
  ;;
record)
  python3 - "$HH" <<'PY'
import json, sqlite3, subprocess, sys, time, pathlib
home = pathlib.Path(sys.argv[1]); db = sqlite3.connect(home / "plugin-data" / "abeyance" / "data.db"); db.row_factory = sqlite3.Row
parks = [dict(r) for r in db.execute("SELECT code,status,tool,args_json,classes,created_at,decided_at,executed_at,decided_by FROM parks ORDER BY created_at")]
events = [dict(r) for r in db.execute("SELECT at,code,kind,detail FROM events ORDER BY id")]
url = subprocess.run(["gh", "release", "view", "--repo", "0xkinno/abeyance-demo", "--json", "url", "-q", ".url"],
                     capture_output=True, text=True).stdout.strip()
ver = subprocess.run(["hermes", "--version"], capture_output=True, text=True).stdout.splitlines()[:1]
out = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "hermes": ver, "release_url": url or None,
       "parks": parks, "events": events}
pathlib.Path("eval/results/real_run.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
print(json.dumps(out, indent=1, default=str)[:2000])
PY
  ;;
*) echo "usage: scripts/real_run.sh configure|probe|night|record"; exit 1;;
esac
