"""Part C's numbers for reports/LAB_07.json and LAB_07.md, from results/A.jsonl, results/B.jsonl,
eval/thresholds/claim.yaml and eval/notes/first_failures.csv (checks/FORMATS.md, sections
15.4 to 15.8). Spends nothing.

    python -m eval.report_07              # prints the tables and writes claim, arms, failures, grid
    python -m eval.report_07 --dry-run    # prints only

Definitions (section 15.8): a sweep's value is the measure's mean over its runs, its score
100 x passes / runs; an arm's measure and score are the mean and SD of its sweep values;
the difference is the claim's gain, signed as `gain` says, with its 95% interval from
stats.interval on the two arms' sweep values, overall and in each stratum; pass@k and
pass^k use the claim's k over each arm's tasks; facts_share is facts present over facts
counted over all its runs.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import yaml

from harness import ROOT
from harness.formats import STRATA
from eval.stats import interval, over_tasks, spread

FAILURES = ROOT / "eval" / "notes" / "first_failures.csv"


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else None


def load(arm: str) -> list[dict]:
    path = ROOT / "results" / f"{arm}.jsonl"
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []


def sweep_values(lines: list[dict], strata: set[str] | None = None, score: bool = False) -> list[float]:
    by: dict[int, list[dict]] = defaultdict(list)
    for x in lines:
        if strata is None or x["stratum"] in strata:
            by[x["sweep"]].append(x)
    out = []
    for _, rs in sorted(by.items()):
        out.append(100.0 * sum(bool(r["passed"]) for r in rs) / len(rs) if score else mean(r["measure"] for r in rs))
    return out


def pass_k(lines: list[dict], k: int):
    counts: dict[str, tuple[int, int]] = {}
    for x in lines:
        n, c = counts.get(x["task"], (0, 0))
        counts[x["task"]] = (n + 1, c + bool(x["passed"]))
    if not counts or any(n < k for n, _ in counts.values()):
        return None, None
    return over_tasks(counts, k)


def arm_block(lines: list[dict], spec: dict, k: int) -> dict:
    meas, score = sweep_values(lines), sweep_values(lines, score=True)
    at, hat = pass_k(lines, k)
    present = sum(x["facts"]["present"] for x in lines)
    total = sum(x["facts"]["total"] for x in lines)
    by = {}
    for s in STRATA:
        rs = [x for x in lines if x["stratum"] == s]
        if not rs:
            continue
        sat, shat = pass_k(rs, k)
        by[s] = {"runs": len(rs), "measure": mean(sweep_values(lines, {s})),
                 "score": mean(sweep_values(lines, {s}, score=True)), "pass_at_k": sat, "pass_hat_k": shat}
    return {"way": spec.get("way"), "switches": spec.get("switches") or {}, "runs": len(lines),
            "measure": {"mean": mean(meas), "sd": spread(meas)}, "score": {"mean": mean(score), "sd": spread(score)},
            "pass_at_k": at, "pass_hat_k": hat, "facts_share": present / total if total else None,
            "cost_per_run_usd": mean(x["cost_usd"] for x in lines),
            "no_tools": sum(1 for x in lines if x["metrics"]["no_tools"]), "by_stratum": by}


def signed(spec: dict, a: list[float], b: list[float]):
    return interval(b, a) if str(spec.get("gain", "")).replace(" ", "") == "B-A" else interval(a, b)


def failures_block(a: list[dict], b: list[dict]) -> tuple[list[dict], dict, list[str]]:
    failed = {x["run_id"]: arm for arm, lines in (("A", a), ("B", b)) for x in lines if not x["passed"]}
    rows = {}
    if FAILURES.exists():
        with FAILURES.open() as f:
            rows = {r["run_id"]: r for r in csv.DictReader(f)}
    out, grid, todo = [], {"A": {}, "B": {}}, []
    for rid, arm in sorted(failed.items()):
        r = rows.get(rid) or {}
        lg, fw = (r.get("last_good") or "").strip(), (r.get("first_wrong") or "").strip()
        if not lg or not fw:
            todo.append(rid)
            continue
        out.append({"run_id": rid, "arm": arm, "last_good": lg, "first_wrong": fw})
        grid[arm].setdefault(lg, {})
        grid[arm][lg][fw] = grid[arm][lg].get(fw, 0) + 1
    return out, grid, todo


def fmt(v, d=3):
    return "—" if v is None else (f"{v:.{d}f}" if isinstance(v, float) else str(v))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    spec = yaml.safe_load((ROOT / "eval" / "thresholds" / "claim.yaml").read_text())
    k = int(spec["k"])
    a, b = load("A"), load("B")
    arms = {"A": arm_block(a, spec["arm_a"], k), "B": arm_block(b, spec["arm_b"], k)}

    av, bv = sweep_values(a), sweep_values(b)
    diff, lo, hi = signed(spec, av, bv)
    by = {}
    for s in STRATA:
        sa, sb = sweep_values(a, {s}), sweep_values(b, {s})
        if len(sa) >= 2 and len(sb) >= 2:
            d, l, h = signed(spec, sa, sb)
            by[s] = {"difference": d, "interval": [l, h]}
    bar, floor = spec["bar"], spec["group_floor"]
    verdict = ("holds" if lo > bar and all(v["difference"] >= floor for v in by.values())
               else "fails" if hi < bar else "cannot_settle")
    claim = {key: spec[key] for key in ("claim", "measure", "gain", "k", "sweeps", "s_a", "s_b", "delta",
                                        "n_needed", "price_usd")}
    claim.update({"difference": diff, "interval": [lo, hi], "by_stratum": by, "verdict": verdict})

    print(f"claim {spec['claim']}: gain {spec['gain']} in {spec['measure']}; bar {bar}, group floor {floor}, k {k}")
    print(f"sweep values  A {[round(v, 3) for v in av]}   B {[round(v, 3) for v in bv]}")
    print(f"scores        A {[round(v, 1) for v in sweep_values(a, score=True)]}   B {[round(v, 1) for v in sweep_values(b, score=True)]}")
    print("\n| Arm | Runs | Measure: mean (SD) | Score: mean (SD) | pass@k | pass^k | Facts right | Cost per run |")
    print("|---|---|---|---|---|---|---|---|")
    for n, x in arms.items():
        print(f"| {n} `{x['way']}` | {x['runs']} | {fmt(x['measure']['mean'])} ({fmt(x['measure']['sd'])}) | "
              f"{fmt(x['score']['mean'], 1)} ({fmt(x['score']['sd'], 1)}) | {fmt(x['pass_at_k'])} | {fmt(x['pass_hat_k'])} | "
              f"{fmt(x['facts_share'])} | ${fmt(x['cost_per_run_usd'], 4)} |")
    print("\n| Stratum | Gain | 95% interval |\n|---|---|---|")
    print(f"| All tasks | {diff:.3f} | [{lo:.3f}, {hi:.3f}] |")
    for s in STRATA:
        if s in by:
            print(f"| {s} | {by[s]['difference']:.3f} | [{by[s]['interval'][0]:.3f}, {by[s]['interval'][1]:.3f}] |")
    print("\nper stratum, by arm (runs, measure, score, pass@k, pass^k):")
    for n, x in arms.items():
        for s, v in x["by_stratum"].items():
            print(f"  {n} {s:15} {v['runs']:3} {fmt(v['measure'])} {fmt(v['score'], 1)} {fmt(v['pass_at_k'])} {fmt(v['pass_hat_k'])}")
    print(f"\nverdict: {verdict}   no-tool runs: A {arms['A']['no_tools']}, B {arms['B']['no_tools']}")

    failures, grid, todo = failures_block(a, b)
    print(f"failed runs: {sum(not x['passed'] for x in a)} in A, {sum(not x['passed'] for x in b)} in B; "
          f"{len(todo)} still need last_good and first_wrong in {FAILURES.relative_to(ROOT)}")
    for arm in ("A", "B"):
        print(f"grid {arm}: {json.dumps(grid[arm])}")

    if not args.dry_run:
        path = ROOT / "reports" / "LAB_07.json"
        report = json.loads(path.read_text())
        report.update({"claim": claim, "arms": arms, "failures": failures, "grid": grid})
        path.write_text(json.dumps(report, indent=2) + "\n")
        print(f"wrote claim, arms, failures and grid into {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
