from __future__ import annotations
import os, time, json
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .models import AnswerRequest, AnswerResponse, TracingInfo
from .observability import init_logging, span, logger, append_metrics_row
from . import llm_client
from . import ensure_env_from_ssm

init_logging()
app = FastAPI(title="LLMOps Starter API", version="0.3.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="ui")

TIMEOUT_SECONDS = float(os.getenv("TIMEOUT_SECONDS", "8"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "2"))
ensure_env_from_ssm("DEMO_API_KEY", "SSM_DEMO_API_KEY", decrypt=True)
DEMO_API_KEY = os.getenv("DEMO_API_KEY")

@app.get("/health")
def health():
    return {"status": "ok"}

def _is_valid_answer(text: str) -> bool:
    return bool(text and text.strip() and len(text.strip()) >= 3)

def _fallback_answer(_: str) -> str:
    return ("I'm not confident enough to answer precisely right now. "
            "Could you rephrase or provide a bit more context?")



@app.post("/answer", response_model=AnswerResponse)
def answer(body: AnswerRequest, request: Request, x_api_key: str | None = Header(default=None)):
    # Simple header auth (skip if not configured)
    if DEMO_API_KEY and x_api_key != DEMO_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

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

            if not _is_valid_answer(text):
                trimmed = body.query[:200]
                result = llm_client.complete(trimmed, timeout_s=TIMEOUT_SECONDS, max_retries=MAX_RETRIES)
                text = result.get("content", "")
                guardrail_mode = "trimmed"

            if not _is_valid_answer(text):
                text = _fallback_answer(body.query)
                guardrail_mode = "fallback"

            latency_ms = int((time.perf_counter() - start) * 1000)
            tokens = (result.get("tokens_in", 0) + result.get("tokens_out", 0))
            cost = result.get("cost")
            lf_id = ctx.get("lf_trace_id")

            # <-- push output to Langfuse (v3)
            if callable(ctx.get("set_output")):
                ctx["set_output"]({"answer": text, "guardrail": guardrail_mode})

            trace = TracingInfo(
                request_id=ctx["trace_id"],
                latency_ms=latency_ms,
                token_usage=tokens,
                cost_usd=cost,
                guardrail=guardrail_mode,
                lf_trace_id=lf_id,
            )
            response = AnswerResponse(answer=text, trace=trace)

            logger.info(
                "answer_success",
                trace_id=ctx["trace_id"],
                lf_trace_id=lf_id,
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
                "lf_trace_id": lf_id,
            })

            return response

        except Exception as e:
            latency_ms = int((time.perf_counter() - start) * 1000)
            logger.error("answer_error", error=str(e), latency_ms=latency_ms, trace_id=ctx["trace_id"])
            # Also emit output to Langfuse for failed path
            if callable(ctx.get("set_output")):
                ctx["set_output"]({"error": str(e), "guardrail": "fallback"})
            trace = TracingInfo(
                request_id=ctx["trace_id"],
                latency_ms=latency_ms,
                token_usage=None,
                cost_usd=None,
                guardrail="fallback",
                lf_trace_id=ctx.get("lf_trace_id"),
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
