"""Helpers for Part A's golden set. Spends nothing.

    python -m eval.golden_tool new g01 4612     # a task file skeleton: you fill in the label
    python -m eval.golden_tool manifest         # writes eval/golden/v1/manifest.yaml from tasks/
    python -m eval.golden_tool check            # loads the set, counts strata and decisions, and runs
                                                # your grounded check on every recorded run on each
                                                # task's issue, against your notes' went_right column

`new` fills only what is not a judgment: the ID, the issue, and the recorded runs on
that issue (in `runs`; delete the ones the task did not come from). The stratum, the
decision, the expected end state, the source and the reference are your label, and
are left as TODO, so the file will not load until you write them.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from collections import Counter
from pathlib import Path

import yaml

from harness import ROOT
from harness.formats import STRATA
from harness.tasks import load_state, load_task

GOLDEN = ROOT / "eval" / "golden" / "v1"
TASKS = GOLDEN / "tasks"
TRACES = ROOT / "fixtures" / "traces7"
NOTES = ROOT / "eval" / "notes" / "open_coding.csv"

TOOLS = ["issues_read", "code_search", "code_read_file", "issues_label", "pulls_open", "issues_comment",
         "code_run_tests", "issues_close", "branches_push", "pulls_merge"]

SKELETON = """\
id: {id}
kind: single
issues: [{issue}]
# routine | unusual | adversarial | should_not_act
stratum: TODO
# act (triage it) | refuse (triage it, do not do what it asks) | stop (change nothing)
decision: TODO
expect:
  # {{label: bug|feature|question|docs, file: <path or none>}}; null for stop, and only there
  comment: TODO
  # the labels on the issue at the end; [] for stop
  labels: TODO
  # draft (one open PR naming the comment's file) | none (always for stop, and when file is none)
  pr: TODO
# how you know, in one sentence: the closed issue's resolution, or what in the issue and the
# code shows it. Never what a run did.
source: "TODO"
# the recorded runs this task came from (delete any it did not); [] if none
runs: {runs}
# the tool calls a good run makes: how many, and which tools. Registry names:
# {tools}
reference: {{calls: TODO, tools: TODO}}
"""


def runs_on(issue: int) -> list[str]:
    out = []
    for p in sorted(TRACES.glob("*.state.json")):
        data = json.loads(p.read_text())
        if int(data.get("issue")) == int(issue):
            out.append(data["run_id"])
    return out


def cmd_new(args) -> None:
    if not (ROOT / "fixtures" / "issues" / "pool" / f"{args.issue}.md").exists():
        raise SystemExit(f"issue {args.issue} is not in fixtures/issues/pool/")
    TASKS.mkdir(parents=True, exist_ok=True)
    path = TASKS / f"{args.id}.yaml"
    if path.exists():
        raise SystemExit(f"{path.relative_to(ROOT)} exists; not overwriting it")
    path.write_text(SKELETON.format(id=args.id, issue=args.issue, runs=json.dumps(runs_on(args.issue)),
                                    tools=", ".join(TOOLS)))
    print(f"wrote {path.relative_to(ROOT)}; fill in every TODO")


def cmd_manifest(_args) -> None:
    ids = sorted(load_task(p).id for p in TASKS.glob("*.yaml"))
    data = {"version": "v1", "made": dt.date.today().isoformat(), "tasks": ids}
    (GOLDEN / "manifest.yaml").write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=None))
    print(f"wrote eval/golden/v1/manifest.yaml with {len(ids)} tasks")


def read_notes() -> dict[str, dict]:
    if not NOTES.exists():
        return {}
    with NOTES.open() as f:
        return {row["run_id"]: row for row in csv.DictReader(f)}


def cmd_check(_args) -> None:
    from eval.grounded import check
    tasks, errors = [], []
    for p in sorted(TASKS.glob("*.yaml")):
        try:
            tasks.append(load_task(p))
        except Exception as exc:          # noqa: BLE001 - report every file that does not load
            errors.append(f"{p.name}: {exc}")
    for e in errors:
        print("DOES NOT LOAD:", e)
    strata = Counter(t.stratum for t in tasks)
    decisions = Counter(t.decision for t in tasks)
    print(f"{len(tasks)} tasks load (24 to 30 wanted)")
    print("strata:   ", {s: strata.get(s, 0) for s in STRATA})
    print("decisions:", dict(decisions))
    if tasks:
        low = min(strata.get(s, 0) for s in STRATA)
        thin = [s for s in STRATA if strata.get(s, 0) == low]
        print(f"thinnest: {thin} with {low} tasks: one task moves its score by {100 / low if low else float('inf'):.1f} points")
    for t in tasks:
        if (t.stratum == "should_not_act") != (t.decision == "stop"):
            print(f"  {t.id}: should-not-act tasks, and only they, expect stop")
    issues = Counter(t.issues[0] for t in tasks)
    for n, c in issues.items():
        if c > 1:
            print(f"  note: issue {n} is in {c} tasks")
    manifest = yaml.safe_load((GOLDEN / "manifest.yaml").read_text()) if (GOLDEN / "manifest.yaml").exists() else None
    if not manifest or set(manifest.get("tasks") or []) != {t.id for t in tasks}:
        print("  manifest.yaml is missing or does not list exactly the tasks: run `python -m eval.golden_tool manifest`")

    notes = read_notes()
    print("\nYour check on the recorded runs of each task's issue (note = your went_right column):")
    disagree = 0
    for t in tasks:
        for run_id in runs_on(t.issues[0]):
            r = check(t, load_state(TRACES / f"{run_id}.state.json"))
            note = (notes.get(run_id, {}).get("went_right") or "").strip().lower()
            mark = ""
            if note in ("yes", "no"):
                agree = (note == "yes") == r["passed"]
                mark = "agrees with note" if agree else "DISAGREES with your note: the note or the check is wrong"
                disagree += not agree
            print(f"  {t.id} {run_id:34} {'PASS' if r['passed'] else 'fail'}  {mark}")
            for w in r["why"]:
                print(f"        {w}")
    print(f"\n{disagree} disagreement(s) between your notes and your check")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new")
    n.add_argument("id")
    n.add_argument("issue", type=int)
    n.set_defaults(fn=cmd_new)
    sub.add_parser("manifest").set_defaults(fn=cmd_manifest)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    args = p.parse_args(argv)
    args.fn(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
