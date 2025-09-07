#!/usr/bin/env bash
set -euo pipefail

# Resolve repo root (this script lives in scripts/)
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Timeouts/retries (can be overridden from shell)
export TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-8}"
export MAX_RETRIES="${MAX_RETRIES:-2}"

# Pin metrics to data/ and ensure directory exists
export METRICS_LOG="${METRICS_LOG:-$ROOT_DIR/data/metrics.jsonl}"
mkdir -p "$(dirname "$METRICS_LOG")"

# Toggle to simulate a transient failure on the first call:
# export LLM_MOCK_FAIL_FIRST=true

# Run API; UI is available at http://localhost:8000/ui/index.html
uvicorn app.main:app \
  --app-dir "$ROOT_DIR/backend" \
  --reload \
  --host 0.0.0.0 \
  --port 8000
