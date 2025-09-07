"""
Read METRICS_LOG (JSONL) and plot cost_usd vs latency_ms.
Usage:
  python scripts/plot_metrics.py ./metrics.jsonl out.png
"""
import sys, json
import matplotlib.pyplot as plt

def main():
    if len(sys.argv) < 3:
        print("Usage: python scripts/plot_metrics.py <metrics.jsonl> <out.png>")
        sys.exit(1)
    src, out = sys.argv[1], sys.argv[2]
    xs, ys = [], []
    with open(src, "r", encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
                cost = row.get("cost_usd")
                lat = row.get("latency_ms")
                if cost is None or lat is None:
                    continue
                xs.append(cost)
                ys.append(lat)
            except json.JSONDecodeError:
                pass
    plt.figure()
    plt.scatter(xs, ys)
    plt.xlabel("cost_usd")
    plt.ylabel("latency_ms")
    plt.title("Cost vs Latency")
    plt.grid(True)
    plt.savefig(out, dpi=160, bbox_inches="tight")
    print(f"Saved plot to {out}")

if __name__ == "__main__":
    main()
