#!/usr/bin/env bash
# MUHR test runner (POSIX).
set -euo pipefail
cd "$(dirname "$0")"

python -m pip install -q -r requirements-dev.txt

echo "=== Python tests ==="
python -m pytest -q tests/

echo "=== Frontend typecheck, tests and build ==="
( cd front-end/muhr-nexus && npm ci --no-audit --no-fund && npx tsc -p tsconfig.app.json --noEmit && npm test && npm run build )

echo "Optional: with services running, python scripts/test_e2e_smoke.py"
