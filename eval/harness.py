
from __future__ import annotations
import time, json, sys
import httpx
import yaml
from pathlib import Path

"""
Simple evaluation harness:
- Reads `golden_set.yaml`
- Sends each query to the running backend
- Checks if answer contains any of the required keywords
- Prints a CSV-like summary to stdout
Usage:
    python eval/harness.py
Ensure backend is running at http://localhost:8000
"""

GOLDEN = Path(__file__).parent / "golden_set.yaml"
BASE_URL = "http://localhost:8000"

def run():
    data = yaml.safe_load(GOLDEN.read_text())
    client = httpx.Client(timeout=30.0)

    print("id,latency_ms,pass,answer_snippet")
    for item in data:
        q = item["query"]
        must = [w.lower() for w in item.get("must_include", [])]

        start = time.perf_counter()
        r = client.post(f"{BASE_URL}/answer", json={"query": q})
        elapsed = int((time.perf_counter() - start) * 1000)

        if r.status_code != 200:
            print(f"{item['id']},{elapsed},ERROR,HTTP_{r.status_code}")
            continue

        payload = r.json()
        ans = payload["answer"]
        snippet = ans.replace("\n", " ")[:60]
        text = ans.lower()

        passed = any(w in text for w in must) if must else True
        print(f"{item['id']},{elapsed},{'OK' if passed else 'FAIL'},{snippet}")

if __name__ == "__main__":
    run()
