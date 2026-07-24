def budget_violation_rate(violations: list[bool]) -> float:
    return sum(bool(item) for item in violations) / len(violations)
