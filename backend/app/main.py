
from __future__ import annotations
import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .models import AnswerRequest, AnswerResponse, TracingInfo
from .observability import init_logging, span, logger
from . import llm_client

init_logging()
app = FastAPI(title="LLMOps Starter API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/answer", response_model=AnswerResponse)
def answer(body: AnswerRequest):
    if not body.query or not body.query.strip():
        raise HTTPException(status_code=400, detail="Query must be non-empty")

    start = time.perf_counter()
    with span("llm.answer", user_id=body.user_id or "anon") as ctx:
        try:
            result = llm_client.complete(body.query)
            latency_ms = int((time.perf_counter() - start) * 1000)
            trace = TracingInfo(
                request_id=ctx["trace_id"],
                latency_ms=latency_ms,
                token_usage=(result.get("tokens_in", 0) + result.get("tokens_out", 0)),
                cost_usd=result.get("cost"),
            )
            response = AnswerResponse(answer=result["content"], trace=trace)
            logger.info("answer_success",
                        trace_id=ctx["trace_id"],
                        latency_ms=latency_ms,
                        tokens_in=result.get("tokens_in"),
                        tokens_out=result.get("tokens_out"),
                        cost_usd=result.get("cost"))
            return response
        except Exception as e:
            latency_ms = int((time.perf_counter() - start) * 1000)
            logger.error("answer_error", error=str(e), latency_ms=latency_ms)
            raise HTTPException(status_code=500, detail="LLM call failed")
