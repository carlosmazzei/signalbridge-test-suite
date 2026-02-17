#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
venv_activate="$repo_root/.venv/bin/activate"

if [[ ! -f "$venv_activate" ]]; then
  echo "Missing virtual environment at $venv_activate" >&2
  exit 1
fi

source "$venv_activate"
exec ruff format --exclude .pre-commit-cache
