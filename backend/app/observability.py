"""
Lightweight observability/tracing helpers.
- JSON logs via structlog
- Context manager for timing/trace IDs
- Optional Langfuse hook (disable by default; enable via env)
- JSONL metrics appender (one row per request)
"""
from __future__ import annotations
import os
import time
import uuid
import json
from contextlib import contextmanager
import structlog

logger = structlog.get_logger()

USE_LANGFUSE = bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))
if USE_LANGFUSE:
    try:
        from langfuse import Langfuse
        _langfuse = Langfuse(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
            host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        )
    except Exception as e:
        logger.warning("langfuse_import_failed", error=str(e))
        _langfuse = None
else:
    _langfuse = None

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
    File path via METRICS_LOG (default: ./metrics.jsonl).
    """
    path = os.getenv("METRICS_LOG", "./metrics.jsonl")
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning("metrics_write_failed", error=str(e), path=path)

@contextmanager
def span(operation: str, **fields):
    """
    Context manager that yields a dict you can populate; logs on exit.
    Returns a trace_id for correlation.
    """
    trace_id = str(uuid.uuid4())
    start = time.perf_counter()
    event = {"trace_id": trace_id, "operation": operation}
    event.update(fields)

    lf_span = None
    if _langfuse:
        try:
            lf_span = _langfuse.trace(name=operation, metadata=fields)
        except Exception as e:
            logger.warning("langfuse_trace_start_failed", error=str(e))

    try:
        yield {"trace_id": trace_id, "start": start, "fields": fields}
    finally:
        duration_ms = int((time.perf_counter() - start) * 1000)
        event["duration_ms"] = duration_ms

        if lf_span:
            try:
                lf_span.update(metadata={"duration_ms": duration_ms, **fields})
            except Exception as e:
                logger.warning("langfuse_trace_update_failed", error=str(e))

        logger.info("span", **event)
