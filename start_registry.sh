#!/usr/bin/env bash
# Start the MUHR registry from the repo root (keeps muhr.db at the repo root).
set -euo pipefail
cd "$(dirname "$0")"
python -m uvicorn registry.main:app --host 127.0.0.1 --port 8000 --reload
