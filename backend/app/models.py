
from __future__ import annotations
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

class AnswerRequest(BaseModel):
    query: str = Field(..., description="User query/prompt")
    user_id: Optional[str] = Field(default=None, description="Optional user identifier")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Arbitrary metadata")

class TracingInfo(BaseModel):
    request_id: str
    latency_ms: int
    token_usage: int | None = None
    cost_usd: float | None = None

class AnswerResponse(BaseModel):
    answer: str
    trace: TracingInfo
