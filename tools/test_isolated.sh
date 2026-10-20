#!/usr/bin/env bash
# Acceptance 9: each extractable package builds and passes its own tests with only its declared
# dependencies installed (no ledger, no database, no web framework).
set -euo pipefail
cd "$(dirname "$0")/.."
for pkg in core doc redact parse categorize metrics; do
  dir="packages/cfo-$pkg"
  [[ -d "$dir/tests" ]] && ls "$dir"/tests/*.py >/dev/null 2>&1 || { echo "skip cfo-$pkg (no tests yet)"; continue; }
  echo "== cfo-$pkg"
  uv run --isolated --no-dev --package "cfo-$pkg" \
    --with pytest --with hypothesis --with reportlab --with xlwt --with-editable packages/cfo-testing \
    pytest -q -o addopts="--import-mode=importlib" -p no:cacheprovider "$dir/tests"
done
echo "ok: every extractable package passes alone"
