"""Allocate a short's running time to its spoken beats, keeping the opening brisk."""


def narrative_durations(lines: list[str], total: float = 30) -> list[float]:
    if len(lines) not in {5, 6}:
        raise ValueError("A studio story needs five or six beats")
    opening = 3.0
    ceiling = 7.5 if len(lines) == 5 else 6.5
    weights = [max(6, len(line.split())) for line in lines[1:]]
    durations = [max(3.0, min(ceiling, (total - opening) * n / sum(weights))) for n in weights]
    for _ in range(12):
        delta = total - opening - sum(durations)
        movable = [i for i, n in enumerate(durations) if (n < ceiling if delta > 0 else n > 3)]
        if abs(delta) < 0.001 or not movable:
            break
        for i in movable:
            durations[i] = max(3.0, min(ceiling, durations[i] + delta / len(movable)))
    result = [opening, *[round(n, 2) for n in durations]]
    result[-1] = round(total - sum(result[:-1]), 2)
    return result
