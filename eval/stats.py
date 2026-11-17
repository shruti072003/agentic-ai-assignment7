"""Assignment 7, Part B: the statistics of a result (checks/FORMATS.md, section 15.5).

Every function here is yours to write. The checker calls each one on cases of its
own, so keep the names, the arguments and what each returns. Slide numbers are
Lecture 7's.

    from eval.stats import pass_at_k, pass_hat_k, spread, margin, interval, sweeps_needed
    pass_at_k(8, 6, 2)                     # about 0.96 (slide 10)
    interval([63.5, 65.0, ...], [61.0, 63.5, ...])   # (gain, low, high), slide 19's four steps
    margin(1.5, 10, 1.5, 10)               # about 1.31: slide 19, from the spreads alone
"""

from __future__ import annotations

from math import ceil, comb, sqrt

Z95 = 1.96        # 95% of a bell curve lies within 1.96 SE of its middle (slide 17)
POWER_Z = 2.80    # 1.96 + 0.84: 95% confidence and 80% power (Activity 2)


def pass_at_k(n: int, c: int, k: int) -> float:
    """The chance that at least one of k runs picked from n passed, when c of the n
    passed: 1 - C(n - c, k) / C(n, k) (slide 10). k is at most n."""
    if not 0 < k <= n:
        raise ValueError(f"k must be 1 to n ({n}), not {k}")
    if not 0 <= c <= n:
        raise ValueError(f"c must be 0 to n ({n}), not {c}")
    # C(n - c, k) is 0 when fewer than k runs failed: then every pick holds a pass.
    return 1.0 - comb(n - c, k) / comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    """The chance that all k runs picked from n passed, when c of the n passed:
    C(c, k) / C(n, k) (slide 10). Never pass@1 to the kth power."""
    if not 0 < k <= n:
        raise ValueError(f"k must be 1 to n ({n}), not {k}")
    if not 0 <= c <= n:
        raise ValueError(f"c must be 0 to n ({n}), not {c}")
    # Counting, never pass@1 ** k: C(c, k) is 0 when fewer than k runs passed.
    return comb(c, k) / comb(n, k)


def over_tasks(counts: dict[str, tuple[int, int]], k: int) -> tuple[float, float]:
    """pass@k and pass^k averaged over tasks, from each task's (n, c)."""
    if not counts:
        return 0.0, 0.0
    at = [pass_at_k(int(n), int(c), k) for n, c in counts.values()]
    hat = [pass_hat_k(int(n), int(c), k) for n, c in counts.values()]
    return sum(at) / len(at), sum(hat) / len(hat)


def spread(values: list[float]) -> float:
    """The SD of the values: sqrt(sum((v - average)^2) / (n - 1)) (slide 17); 0.0 for
    a single value."""
    values = [float(v) for v in values]
    if len(values) < 2:
        return 0.0
    average = sum(values) / len(values)
    return sqrt(sum((v - average) ** 2 for v in values) / (len(values) - 1))


def margin(s_first: float, n_first: int, s_second: float, n_second: int) -> float:
    """Slide 19's margin from two arms' spreads and sweep counts: 1.96 x the SE of the
    difference, where each arm's SE is s / sqrt(n) and the difference's is
    sqrt(SE_first^2 + SE_second^2). margin(1.5, 10, 1.5, 10) is about 1.31."""
    se_first = s_first / sqrt(n_first)
    se_second = s_second / sqrt(n_second)
    return Z95 * sqrt(se_first ** 2 + se_second ** 2)


def interval(first: list[float], second: list[float]) -> tuple[float, float, float]:
    """Slide 19's four steps for two arms' sweep values: the gain, the average of
    `first` minus the average of `second`, and the low and high ends of its 95%
    interval. The SE of each average is s / sqrt(n); the SE of the difference is
    sqrt(SE_first^2 + SE_second^2); the interval is the gain +/- 1.96 x that SE."""
    first, second = [float(v) for v in first], [float(v) for v in second]
    gain = sum(first) / len(first) - sum(second) / len(second)
    m = margin(spread(first), len(first), spread(second), len(second))
    return gain, gain - m, gain + m


def sweeps_needed(s_a: float, s_b: float, delta: float) -> int:
    """Activity 2's arithmetic: the smallest whole n with
    n >= (s_a^2 + s_b^2) x (2.80 / delta)^2 (Part C, task 4)."""
    if delta <= 0:
        raise ValueError("delta, the smallest gain you would act on, must be positive")
    need = (s_a ** 2 + s_b ** 2) * (POWER_Z / delta) ** 2
    # The small tolerance keeps a value such as 4.0000000001, float noise, at 4.
    return max(1, ceil(need - 1e-9))
