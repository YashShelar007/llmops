from __future__ import annotations
import os, time, json
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .models import AnswerRequest, AnswerResponse, TracingInfo
from .observability import init_logging, span, logger, append_metrics_row
from . import llm_client

init_logging()
app = FastAPI(title="LLMOps Starter API", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the frontend from /ui so you don't need Live Server (prevents auto reload flicker)
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="ui")

TIMEOUT_SECONDS = float(os.getenv("TIMEOUT_SECONDS", "8"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "2"))

@app.get("/health")
def health():
    return {"status": "ok"}

def _is_valid_answer(text: str) -> bool:
    # simple sanity checks; extend with stricter rules or schemas if needed
    if not text or not text.strip():
        return False
    if len(text.strip()) < 3:
        return False
    return True

def _fallback_answer(prompt: str) -> str:
    return ("I'm not confident enough to answer precisely right now. "
            "Could you rephrase or provide a bit more context?")

@app.post("/answer", response_model=AnswerResponse)
def answer(body: AnswerRequest, request: Request):
    if not body.query or not body.query.strip():
        raise HTTPException(status_code=400, detail="Query must be non-empty")

    client_host = request.client.host if request.client else "unknown"
    query_len = len(body.query)
    user_id = body.user_id or "anon"

    start = time.perf_counter()
    guardrail_mode = "none"

    with span("llm.answer", user_id=user_id, client_host=client_host, query_len=query_len) as ctx:
        try:
            result = llm_client.complete(body.query, timeout_s=TIMEOUT_SECONDS, max_retries=MAX_RETRIES)
            text = result.get("content", "")

            # Guardrail pass #1: invalid → try trimmed prompt
            if not _is_valid_answer(text):
                trimmed = body.query[:200]
                result = llm_client.complete(trimmed, timeout_s=TIMEOUT_SECONDS, max_retries=MAX_RETRIES)
                text = result.get("content", "")
                guardrail_mode = "trimmed"

            # Guardrail pass #2: still invalid → safe fallback
            if not _is_valid_answer(text):
                text = _fallback_answer(body.query)
                guardrail_mode = "fallback"

            latency_ms = int((time.perf_counter() - start) * 1000)
            tokens = (result.get("tokens_in", 0) + result.get("tokens_out", 0))
            cost = result.get("cost")

            trace = TracingInfo(
                request_id=ctx["trace_id"],
                latency_ms=latency_ms,
                token_usage=tokens,
                cost_usd=cost,
                guardrail=guardrail_mode,
            )
            response = AnswerResponse(answer=text, trace=trace)

            logger.info(
                "answer_success",
                trace_id=ctx["trace_id"],
                user_id=user_id,
                client_host=client_host,
                latency_ms=latency_ms,
                tokens_in=result.get("tokens_in"),
                tokens_out=result.get("tokens_out"),
                cost_usd=cost,
                guardrail=guardrail_mode,
            )

            append_metrics_row({
                "ts": time.time(),
                "trace_id": ctx["trace_id"],
                "user_id": user_id,
                "latency_ms": latency_ms,
                "tokens_in": result.get("tokens_in"),
                "tokens_out": result.get("tokens_out"),
                "cost_usd": cost,
                "query_len": query_len,
                "guardrail": guardrail_mode,
            })

            return response

        except Exception as e:
            latency_ms = int((time.perf_counter() - start) * 1000)
            logger.error("answer_error", error=str(e), latency_ms=latency_ms, trace_id=ctx["trace_id"])
            # Safe fallback on provider exception
            trace = TracingInfo(
                request_id=ctx["trace_id"],
                latency_ms=latency_ms,
                token_usage=None,
                cost_usd=None,
                guardrail="fallback",
            )
            return AnswerResponse(answer=_fallback_answer(body.query), trace=trace)

@app.get("/metrics")
def get_metrics(limit: int = 50):
    path = os.getenv("METRICS_LOG", "./metrics.jsonl")
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()[-limit:]
        items = [json.loads(x) for x in lines if x.strip()]
    except FileNotFoundError:
        items = []
    return {"items": items}
