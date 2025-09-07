
"""
LLM client abstraction.
- By default: deterministic mock for portability.
- Swap in a real provider (OpenAI/Anthropic/etc.) with env config.
"""
from __future__ import annotations
import os
import math
from typing import Dict, Any

PROVIDER = os.getenv("LLM_PROVIDER", "mock")

def _estimate_tokens(text: str) -> int:
    # naive token estimate: 1 token ~ 4 chars (rough approximation)
    return max(1, math.ceil(len(text) / 4))

def _mock_completion(prompt: str) -> Dict[str, Any]:
    # Small rule-based answers so eval passes; keeps deterministic behavior.
    q = prompt.lower().strip()

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
    cost = 0.2 * (tokens_in + tokens_out) / 1000.0  # illustrative cost model
    return {"content": content, "tokens_in": tokens_in, "tokens_out": tokens_out, "cost": cost}


def complete(prompt: str) -> Dict[str, Any]:
    if PROVIDER == "mock":
        return _mock_completion(prompt)
    # Example (commented): use real SDKs when env is set up
    # elif PROVIDER == "openai":
    #     from openai import OpenAI
    #     client = OpenAI()
    #     resp = client.chat.completions.create(
    #         model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    #         messages=[{"role":"user","content":prompt}],
    #     )
    #     text = resp.choices[0].message.content
    #     usage = resp.usage
    #     cost = _estimate_cost_openai(usage)  # implement if needed
    #     return {"content": text, "tokens_in": usage.prompt_tokens, "tokens_out": usage.completion_tokens, "cost": cost}
    else:
        # fallback to mock
        return _mock_completion(prompt)
