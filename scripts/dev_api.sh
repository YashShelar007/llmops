#!/usr/bin/env bash
set -euo pipefail

# Resolve repo root (this script lives in scripts/)
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Auto-load .env if present (exports all vars)
if [ -f "$ROOT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ROOT_DIR/.env"
  echo "LF host=${LANGFUSE_HOST:-unset}, PK prefix=${LANGFUSE_PUBLIC_KEY:0:10}"
  set +a
fi

# Timeouts/retries (can be overridden from shell)
export TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-8}"
export MAX_RETRIES="${MAX_RETRIES:-2}"

# Pin metrics to data/ and ensure directory exists
export METRICS_LOG="${METRICS_LOG:-$ROOT_DIR/data/metrics.jsonl}"
mkdir -p "$(dirname "$METRICS_LOG")"

# Give OpenTelemetry a service name and some basic attributes
export OTEL_SERVICE_NAME="${OTEL_SERVICE_NAME:-llmops-starter-api}"
export OTEL_RESOURCE_ATTRIBUTES="${OTEL_RESOURCE_ATTRIBUTES:-service.version=${APP_VERSION:-0.3.1},deployment.environment=dev}"

# Prefer the project venv's python; fall back to system python if not found
PY_BIN="${PY_BIN:-$ROOT_DIR/.venv/bin/python}"
if [ ! -x "$PY_BIN" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PY_BIN="$(command -v python3)"
  else
    PY_BIN="$(command -v python)"
  fi
  echo "Warning: project venv not found at $ROOT_DIR/.venv; using: $PY_BIN"
else
  echo "Using project venv: $PY_BIN"
fi

# Optional debug to confirm Langfuse env is loaded
echo "METRICS_LOG=$METRICS_LOG"
echo "LANGFUSE_HOST=${LANGFUSE_HOST:-unset}"
echo "LANGFUSE_PUBLIC_KEY prefix: ${LANGFUSE_PUBLIC_KEY:-unset}" | sed 's/\(.\{30\}\).*/\1.../'

# Toggle to simulate a transient failure on the first call:
# export LLM_MOCK_FAIL_FIRST=true

# Run API with the chosen interpreter so uvicorn/deps come from the same env
exec "$PY_BIN" -m uvicorn app.main:app \
  --app-dir "$ROOT_DIR/backend" \
  --reload \
  --host 0.0.0.0 \
  --port 8000
