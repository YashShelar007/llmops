#!/usr/bin/env bash
set -euo pipefail
export TIMEOUT_SECONDS=${TIMEOUT_SECONDS:-8}
export MAX_RETRIES=${MAX_RETRIES:-2}
# Toggle to test retry path:
# export LLM_MOCK_FAIL_FIRST=true
uvicorn app.main:app --app-dir backend --reload --host 0.0.0.0 --port 8000
