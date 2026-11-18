"""Read Part D's outputs to label, one at a time. Spends nothing, and makes no judgment.

    python -m eval.show_judge j07            # the issue, every tool call with its full result, then the comment
    python -m eval.show_judge j07 --short    # results cut to 800 characters
    python -m eval.show_judge --todo         # the outputs eval/labels/labels.csv does not label yet

The system that wrote each output is left out on purpose, so it cannot sway a label.
The labels and reasons are yours (no assistant writes or suggests one).
"""

from __future__ import annotations

import argparse
import csv
import json
import textwrap

from harness import ROOT

OUTPUTS = ROOT / "fixtures" / "judge" / "outputs"
LABELS = ROOT / "eval" / "labels" / "labels.csv"


def show(oid: str, short: bool) -> None:
    d = json.loads((OUTPUTS / f"{oid}.json").read_text())
    issue = d["issue"]
    print(f"OUTPUT {d['id']}   issue #{issue.get('number')}: {issue.get('title')}")
    print("-" * 80)
    print(textwrap.indent(str(issue.get("body") or ""), "  | "))
    print("=" * 80)
    for i, e in enumerate(d["evidence"], 1):
        result = str(e.get("result") or "")
        if short and len(result) > 800:
            result = result[:800] + f" ...[{len(result) - 800} more chars]"
        print(f"#{i} {e.get('tool')}({json.dumps(e.get('input'), ensure_ascii=False)})")
        print(textwrap.indent(result, "      "))
    print("=" * 80)
    print("COMMENT:")
    print(textwrap.indent(d["comment"], "  > "))


def todo() -> None:
    done = set()
    if LABELS.exists():
        with LABELS.open() as f:
            done = {r["id"] for r in csv.DictReader(f) if (r.get("label") or "").strip()}
    left = sorted(p.stem for p in OUTPUTS.glob("*.json") if p.stem not in done)
    print(f"{len(left)} to label: {' '.join(left)}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("id", nargs="?")
    p.add_argument("--short", action="store_true")
    p.add_argument("--todo", action="store_true")
    args = p.parse_args(argv)
    if args.todo or not args.id:
        todo()
    else:
        show(args.id, args.short)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
