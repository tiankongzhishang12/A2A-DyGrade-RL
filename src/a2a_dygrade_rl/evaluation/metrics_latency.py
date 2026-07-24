def paper_latency(latencies: list[float]) -> float:
    return max(latencies) if latencies else 0.0
