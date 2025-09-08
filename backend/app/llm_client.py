# backend/app/llm_client.py
from __future__ import annotations
import os, math, random, time
from typing import Dict, Any

from . import ensure_env_from_ssm

PROVIDER = os.getenv("LLM_PROVIDER", "mock")

# Caps / controls (work both locally and in Lambda)
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "300"))
OPENAI_TIMEOUT_S = float(os.getenv("OPENAI_TIMEOUT_S", "8"))

# If OPENAI_API_KEY missing, pull from SSM (runtime-safe)
ensure_env_from_ssm("OPENAI_API_KEY", "SSM_OPENAI_API_KEY", decrypt=True)

def _estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))

# ---------------- mock path (unchanged) ----------------
TIMEOUT_SECONDS = float(os.getenv("TIMEOUT_SECONDS", "8"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "2"))
MOCK_FAIL_FIRST = os.getenv("LLM_MOCK_FAIL_FIRST", "false").lower() == "true"
_failed_once = False

def _mock_completion(prompt: str) -> Dict[str, Any]:
    global _failed_once
    if MOCK_FAIL_FIRST and not _failed_once:
        _failed_once = True
        raise TimeoutError("simulated transient failure (mock)")

    q = prompt.lower().strip()
    if q == "empty":
        return {"content": "", "tokens_in": 1, "tokens_out": 0, "cost": 0.0}
    if "capital of france" in q:
        content = "Paris is the capital of France."
    elif ("sorting algorithm" in q) and ("n log n" in q or "o(n log n)" in q):
        content = "Merge sort or quicksort run in O(n log n) on average."
    elif "explain what an api" in q:
        content = "An API is an interface that enables software systems to communicate via defined requests and responses."
    else:
        content = f"[demo-answer] You asked: {prompt[:120]}"

    tokens_in = _estimate_tokens(prompt)
    tokens_out = _estimate_tokens(content)
    cost = 0.2 * (tokens_in + tokens_out) / 1000.0
    return {"content": content, "tokens_in": tokens_in, "tokens_out": tokens_out, "cost": cost}

# ---------------- openai path ----------------
def _openai_completion(prompt: str) -> Dict[str, Any]:
    from openai import OpenAI
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not configured (env or SSM).")
    client = OpenAI(api_key=api_key)

    # Chat Completions (responses API compatible)
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=OPENAI_MAX_TOKENS,
        timeout=OPENAI_TIMEOUT_S,
    )
    text = resp.choices[0].message.content or ""
    # Usage object may differ by model; guard with getattr
    usage = getattr(resp, "usage", None)
    tin = getattr(usage, "prompt_tokens", None) or 0
    tout = getattr(usage, "completion_tokens", None) or 0
    # your internal mock price math kept (we’re not relying on OpenAI prices here)
    cost = 0.000001 * (tin + tout)  # placeholder; you can calibrate later
    return {"content": text, "tokens_in": tin, "tokens_out": tout, "cost": cost}

def _complete_once(prompt: str, timeout_s: float):
    if PROVIDER == "openai":
        return _openai_completion(prompt)
    return _mock_completion(prompt)

def complete(prompt: str, timeout_s: float | None = None, max_retries: int | None = None) -> Dict[str, Any]:
    timeout_s = timeout_s or TIMEOUT_SECONDS
    attempts = (max_retries if max_retries is not None else MAX_RETRIES) + 1
    backoff = 0.35
    for i in range(attempts):
        try:
            return _complete_once(prompt, timeout_s)
        except Exception:
            if i == attempts - 1:
                raise
            sleep_for = backoff * (1.0 + random.random())
            time.sleep(sleep_for)
            backoff *= 1.8
