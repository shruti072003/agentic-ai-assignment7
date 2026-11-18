"""Part C, task 3 and 4: what the first three sweeps may tell you before the bar is set.

    python -m eval.prebar --claim plan --arm-a arm_planned --arm-b agent [--delta 0.2 --delta 0.5]

Prints only each arm's spread s (the SD of its sweep values of the measure, over the
sweeps run so far) and the mean cost of one sweep, then the sweeps and the price each
candidate delta would need. It never prints an arm's mean, its score or a difference
between the arms: the comparison waits until eval/thresholds/claim.yaml is pushed
(slide 16). Spends nothing.
"""

from __future__ import annotations

import argparse
from collections import defaultdict

from eval.results_07 import parse_switches, results
from eval.stats import spread, sweeps_needed


def arm_numbers(way: str, switches: dict, claim: str, tasks: str, subset: str, max_sweep: int) -> dict:
    lines = [x for x in results("-", way, switches, claim, tasks, subset) if (x["sweep"] or 0) <= max_sweep]
    by_sweep: dict[int, list[dict]] = defaultdict(list)
    for x in lines:
        by_sweep[x["sweep"]].append(x)
    n_tasks = max((len(v) for v in by_sweep.values()), default=0)
    values = [sum(x["measure"] for x in v) / len(v) for _, v in sorted(by_sweep.items())]
    costs = [sum(x["cost_usd"] for x in v) for _, v in sorted(by_sweep.items())]
    return {"runs": len(lines), "sweeps": {s: len(v) for s, v in sorted(by_sweep.items())}, "tasks": n_tasks,
            "s": spread(values), "cost_per_sweep": sum(costs) / len(costs) if costs else 0.0}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--claim", required=True, choices=["tokens", "plan", "examples", "checkpoint", "split"])
    p.add_argument("--arm-a", required=True)
    p.add_argument("--arm-b", required=True)
    p.add_argument("--switch-a", action="append", default=[])
    p.add_argument("--switch-b", action="append", default=[])
    p.add_argument("--tasks", default="eval/golden/v1/tasks")
    p.add_argument("--subset", default="eval/subsets/claim.txt")
    p.add_argument("--max-sweep", type=int, default=3)
    p.add_argument("--delta", type=float, action="append", default=[])
    args = p.parse_args(argv)

    a = arm_numbers(args.arm_a, parse_switches(args.switch_a), args.claim, args.tasks, args.subset, args.max_sweep)
    b = arm_numbers(args.arm_b, parse_switches(args.switch_b), args.claim, args.tasks, args.subset, args.max_sweep)
    for name, arm, way in (("A", a, args.arm_a), ("B", b, args.arm_b)):
        print(f"arm {name} ({way}): {arm['runs']} finished runs, per sweep {arm['sweeps']}; "
              f"s = {arm['s']:.4f}; cost of one sweep ${arm['cost_per_sweep']:.4f}")
    both = (a["cost_per_sweep"] + b["cost_per_sweep"]) / 2
    step = 1 / a["tasks"] if a["tasks"] else 0.1
    print(f"mean cost of one sweep over both arms: ${both:.4f}")
    print(f"one step of a sweep's value (a count of one over {a['tasks']} tasks): {step:.3f}")
    s_a = a["s"] if a["s"] > 0 else step
    s_b = b["s"] if b["s"] > 0 else step
    if a["s"] == 0 or b["s"] == 0:
        print(f"an arm's s is 0: sized with one step instead (s_a = {s_a:.3f}, s_b = {s_b:.3f})")
    for d in args.delta:
        n = sweeps_needed(s_a, s_b, d)
        print(f"  delta {d}: n >= ({s_a:.3f}^2 + {s_b:.3f}^2) x (2.80/{d})^2 -> {n} sweeps per arm; "
              f"price {n} x 2 x ${both:.4f} = ${n * 2 * both:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
