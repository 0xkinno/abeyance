#!/usr/bin/env bash
# Codespaces setup: Hermes from source in its own venv, Abeyance linked as a user plugin.
# Secrets come from Codespaces secrets as environment variables; nothing is written to files here.
set -euo pipefail
pip install --quiet uv pytest
HERMES_SRC="${HERMES_SRC:-/workspaces/hermes-agent}"
[ -d "$HERMES_SRC" ] || git clone --depth 1 https://github.com/NousResearch/hermes-agent.git "$HERMES_SRC"
UV_PROJECT_ENVIRONMENT="$HOME/.hermes-venv" uv sync --frozen --project "$HERMES_SRC"
mkdir -p "$HOME/.local/bin" "$HOME/.hermes/plugins"
ln -sf "$HOME/.hermes-venv/bin/hermes" "$HOME/.local/bin/hermes"
ln -sfn "$(pwd)/abeyance" "$HOME/.hermes/plugins/abeyance"
hermes plugins enable abeyance || true
python -m pytest -q tests
echo "Ready. Next: docs/CODESPACES.md"
