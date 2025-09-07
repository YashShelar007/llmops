"""
LLM client abstraction.
- Default: deterministic mock for portability.
- Adds timeout + bounded retries with jitter.
- Optional test flag LLM_MOCK_FAIL_FIRST=true to simulate a transient failure.
"""
from __future__ import annotations
import os, math, random, time
from typing import Dict, Any

PROVIDER = os.getenv("LLM_PROVIDER", "mock")
TIMEOUT_SECONDS = float(os.getenv("TIMEOUT_SECONDS", "8"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "2"))
MOCK_FAIL_FIRST = os.getenv("LLM_MOCK_FAIL_FIRST", "false").lower() == "true"
_failed_once = False  # stateful within process to simulate one transient failure

def _estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))

def _mock_completion(prompt: str) -> Dict[str, Any]:
    global _failed_once
    # Simulate a transient failure on first call if enabled
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
    cost = 0.2 * (tokens_in + tokens_out) / 1000.0  # illustrative
    return {"content": content, "tokens_in": tokens_in, "tokens_out": tokens_out, "cost": cost}

def _complete_once(prompt: str, timeout_s: float) -> Dict[str, Any]:
    # For real SDKs you would honor timeout_s (client options / httpx timeout).
    if PROVIDER == "mock":
        return _mock_completion(prompt)
    # elif PROVIDER == "openai":
    #     ...
    return _mock_completion(prompt)

def complete(prompt: str, timeout_s: float | None = None, max_retries: int | None = None) -> Dict[str, Any]:
    """
    Call provider with bounded retries + jitter.
    """
    timeout_s = timeout_s or TIMEOUT_SECONDS
    attempts = (max_retries if max_retries is not None else MAX_RETRIES) + 1  # first try + retries
    backoff = 0.35

    for i in range(attempts):
        try:
            return _complete_once(prompt, timeout_s)
        except Exception as e:
            last = (i == attempts - 1)
            if last:
                raise
            # jittered backoff
            sleep_for = backoff * (1.0 + random.random())
            time.sleep(sleep_for)
            backoff *= 1.8
