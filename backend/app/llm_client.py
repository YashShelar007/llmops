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

# OpenAI client (v1)
try:
    from openai import OpenAI  # pip install openai>=1.45
    _has_openai = True
except Exception:
    _has_openai = False

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "300"))

# rough price map (USD / 1K tokens). Adjust if you switch models.
_PRICE = {
    "gpt-4o-mini": {"in": 0.00015, "out": 0.0006},
    # add more if you use them…
}

def _price_for(model: str, tokens_in: int, tokens_out: int) -> float:
    p = _PRICE.get(model, {"in": 0.0, "out": 0.0})
    return (tokens_in * p["in"] + tokens_out * p["out"]) / 1000.0

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
    if PROVIDER == "mock":
        return _mock_completion(prompt)

    if PROVIDER == "openai":
        if not _has_openai:
            raise RuntimeError("openai package not installed")
        client = OpenAI()  # reads OPENAI_API_KEY from env
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=OPENAI_MAX_TOKENS,
            temperature=0.2,
        )
        content = resp.choices[0].message.content or ""
        # usage is present on paid models
        t_in = getattr(resp, "usage", None).prompt_tokens if getattr(resp, "usage", None) else len(prompt) // 4
        t_out = getattr(resp, "usage", None).completion_tokens if getattr(resp, "usage", None) else len(content) // 4
        return {
            "content": content,
            "tokens_in": int(t_in),
            "tokens_out": int(t_out),
            "cost": _price_for(OPENAI_MODEL, int(t_in), int(t_out)),
        }

    # default fallback stays as mock
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
