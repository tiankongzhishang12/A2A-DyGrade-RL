def useful_communication_rate(useful: list[bool]) -> float:
    return sum(bool(item) for item in useful) / len(useful) if useful else 0.0


def disagreement_reduction(before: list[float], after: list[float]) -> float:
    if not before:
        return 0.0
    return sum(b - a for b, a in zip(before, after)) / len(before)
