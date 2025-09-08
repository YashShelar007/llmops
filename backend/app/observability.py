# backend/app/observability.py
"""
Langfuse v3-compatible observability helpers.
- JSON logs via structlog
- Context manager for timing/trace IDs
- Optional Langfuse hook (enable via env: LANGFUSE_PUBLIC_KEY/SECRET_KEY/HOST)
- Metrics JSONL writer (defaults to /tmp on Lambda, with fallback)
"""
from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import contextmanager
from typing import Any, Dict, Generator

import structlog
from . import ensure_env_from_ssm  # expects helper in app __init__.py (or similar)

logger = structlog.get_logger()

# Make metrics writable on Lambda by default
DEFAULT_METRICS = "/tmp/metrics.jsonl" if os.getenv("AWS_LAMBDA_FUNCTION_NAME") else "./metrics.jsonl"

# Hydrate Langfuse env from SSM if present
ensure_env_from_ssm("LANGFUSE_PUBLIC_KEY", "SSM_LANGFUSE_PUBLIC_KEY", decrypt=True)
ensure_env_from_ssm("LANGFUSE_SECRET_KEY", "SSM_LANGFUSE_SECRET_KEY", decrypt=True)
ensure_env_from_ssm("LANGFUSE_HOST",       "SSM_LANGFUSE_HOST",       decrypt=False)

# ---- Langfuse (v3) client wiring -------------------------------------------
USE_LANGFUSE = all(os.getenv(k) for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"))
_langfuse = None
if USE_LANGFUSE:
    try:
        from langfuse import get_client
        _langfuse = get_client()  # picks up env vars
    except Exception as e:
        logger.warning("langfuse_import_failed", error=str(e))
        _langfuse = None

# Current OTel span accessor (Langfuse v3 uses OpenTelemetry under the hood)
try:
    from opentelemetry.trace import get_current_span
except Exception:
    get_current_span = None  # gracefully degrade

# ---- logging & metrics -------------------------------------------------------
def init_logging():
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.EventRenamer("message"),
            structlog.processors.JSONRenderer(),
        ]
    )

def append_metrics_row(row: dict):
    """
    Append a single JSON object to a metrics JSONL file.
    Path via METRICS_LOG (default: DEFAULT_METRICS). Ensures directory exists.
    Falls back to /tmp/metrics.jsonl on read-only FS (Lambda).
    """
    path = os.getenv("METRICS_LOG", DEFAULT_METRICS)

    def _write(p: str):
        dirpath = os.path.dirname(p) or "."
        os.makedirs(dirpath, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    try:
        _write(path)
    except OSError as e:
        # 30: Read-only file system, 13: Permission denied
        if e.errno in (30, 13):
            fallback = "/tmp/metrics.jsonl"
            try:
                _write(fallback)
                logger.info("metrics_write_fallback", from_path=path, to_path=fallback)
                return
            except Exception as e2:
                logger.warning("metrics_write_fallback_failed", error=str(e2), fallback=fallback)
        # Any other error or fallback failed
        logger.warning("metrics_write_failed", error=str(e), path=path)

# ---- span helper -------------------------------------------------------------
@contextmanager
def span(operation: str, **fields) -> Generator[Dict[str, Any], None, None]:
    """
    Yields a ctx dict containing:
      - trace_id: app-level UUID
      - lf_trace_id: OTel trace id (32-hex) if Langfuse enabled
      - set_output(obj): call inside the with-block to send 'output' to Langfuse
    """
    trace_id = str(uuid.uuid4())
    start = time.perf_counter()
    event = {"trace_id": trace_id, "operation": operation}
    event.update(fields)

    lf_cm = None
    lf_obs = None
    lf_trace_id = None
    _out_holder = {"output": None}

    def set_output(obj: Any) -> None:
        _out_holder["output"] = obj
        # Push immediately so Output shows even if something fails later
        if lf_obs is not None and hasattr(lf_obs, "update"):
            try:
                lf_obs.update(output=obj)
            except Exception as e:
                logger.warning("langfuse_update_failed", error=str(e))

    if _langfuse:
        try:
            lf_cm = _langfuse.start_as_current_span(name=operation, input=fields)
            lf_obs = lf_cm.__enter__()  # enter context
            # Pull OTel trace id for the response payload
            if get_current_span:
                try:
                    span_obj = get_current_span()
                    ctx = span_obj.get_span_context()
                    if ctx and getattr(ctx, "trace_id", 0):
                        lf_trace_id = f"{ctx.trace_id:032x}"
                except Exception as e:
                    logger.warning("otel_trace_id_failed", error=str(e))
        except Exception as e:
            logger.warning("langfuse_trace_start_failed", error=str(e))

    try:
        yield {
            "trace_id": trace_id,
            "start": start,
            "fields": fields,
            "lf_trace_id": lf_trace_id,
            "set_output": set_output,
        }
    finally:
        duration_ms = int((time.perf_counter() - start) * 1000)
        event["duration_ms"] = duration_ms

        # Ensure latest output is saved before closing
        if lf_obs and _out_holder["output"] is not None and hasattr(lf_obs, "update"):
            try:
                lf_obs.update(output=_out_holder["output"])
            except Exception as e:
                logger.warning("langfuse_update_failed_final", error=str(e))

        if lf_cm:
            try:
                lf_cm.__exit__(None, None, None)
                # optional but helpful in dev/short runs
                try:
                    _langfuse.flush()
                except Exception:
                    pass
            except Exception as e:
                logger.warning("langfuse_trace_end_failed", error=str(e))

        logger.info("span", **event, lf_trace_id=lf_trace_id)
