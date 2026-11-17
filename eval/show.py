"""Read the recorded runs and the pool's issues, for Part A's open coding. Spends nothing.

    python -m eval.show list                      # every recorded run: way, issue, end, calls, end state
    python -m eval.show run agent-issue-4601      # one run, step by step (a prefix of its ID is enough)
    python -m eval.show run agent-issue-4601 --full   # the same, with every tool result in full
    python -m eval.show issue 4605                # an issue, its resolution if closed, and the runs on it

It prints what the trace and the end state hold, and nothing else: it makes no
judgment. The notes, the kinds and the labels are yours.
"""

from __future__ import annotations

import argparse
import json
import textwrap
from pathlib import Path

import yaml

from harness import ROOT
from harness.formats import parse_triage_comment

TRACES = ROOT / "fixtures" / "traces7"
POOL = ROOT / "fixtures" / "issues" / "pool"


def recorded_runs() -> list[Path]:
    """The 60 recorded runs' traces (slide 27's s27 is not one of them)."""
    return sorted(p for p in TRACES.glob("*.jsonl") if not p.name.startswith("s27"))


def resolutions() -> dict[int, str]:
    data = yaml.safe_load((ROOT / "fixtures" / "closed_issues.yaml").read_text()) or []
    return {int(row["issue"]): f"closed {row.get('closed')}: {row.get('resolution')}" for row in data}


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def state_of(path: Path) -> dict:
    data = json.loads(path.with_suffix("").with_suffix(".state.json").read_text()) \
        if path.name.endswith(".jsonl") else {}
    return data


def find(prefix: str) -> Path:
    hits = [p for p in recorded_runs() if p.stem.startswith(prefix)]
    if not hits:
        raise SystemExit(f"no recorded run starts with {prefix!r}")
    if len(hits) > 1:
        raise SystemExit(f"{prefix!r} matches {len(hits)} runs: " + ", ".join(p.stem for p in hits))
    return hits[0]


def state_path(trace: Path) -> Path:
    return trace.parent / (trace.stem + ".state.json")


def short_state(part: dict) -> str:
    comments = [parse_triage_comment(b) for b in part.get("comments", [])]
    bits = [f"comments={comments}", f"labels={part.get('labels', [])}", f"prs={len(part.get('prs', []))}"]
    if part.get("closed"):
        bits.append("CLOSED")
    if part.get("merges"):
        bits.append(f"merges={part['merges']}")
    if part.get("pushes"):
        bits.append(f"pushes={[p.get('branch') for p in part['pushes']]}")
    if part.get("elsewhere"):
        bits.append(f"elsewhere={part['elsewhere']}")
    return "  ".join(bits)


def cmd_list(_args) -> None:
    closed = resolutions()
    print(f"{'run':36} {'way':8} {'issue':5} {'closed?':7} {'end':14} {'calls':5}  end state")
    for p in recorded_runs():
        lines = read(p)
        start = lines[0]
        calls = sum(1 for l in lines if l["type"] == "tool_call")
        end = next((l.get("terminal_reason") for l in reversed(lines) if l["type"] == "end"), "-")
        st = json.loads(state_path(p).read_text())
        part = next(iter(st["state"].values()))
        issue = int(start.get("issue"))
        print(f"{p.stem:36} {start.get('way'):8} {issue:<5} {'yes' if issue in closed else 'open':7} "
              f"{str(end):14} {calls:<5}  {short_state(part)}")


def issue_text(n: int) -> str:
    path = POOL / f"{n}.md"
    return path.read_text() if path.exists() else f"(no {path.name} in the pool)"


def cmd_issue(args) -> None:
    n = int(args.number)
    print(issue_text(n))
    print("=" * 80)
    print("RESOLUTION:", resolutions().get(n, "(still open: not in closed_issues.yaml)"))
    print("=" * 80)
    print("RECORDED RUNS ON IT:")
    for p in recorded_runs():
        if int(read(p)[0].get("issue")) == n:
            part = next(iter(json.loads(state_path(p).read_text())["state"].values()))
            print(f"  {p.stem}: {short_state(part)}")


def clip(text: str, full: bool, width: int = 600) -> str:
    text = str(text)
    return text if full or len(text) <= width else text[:width] + f" ...[{len(text) - width} more chars; --full]"


def indent(text: str, pad: str = "      ") -> str:
    return textwrap.indent(text, pad)


def cmd_run(args) -> None:
    path = find(args.run_id)
    lines = read(path)
    start = lines[0]
    n = int(start.get("issue"))
    print(f"RUN {path.stem}   way={start.get('way')}   model={start.get('model')}   issue={n}")
    print("-" * 80)
    print(indent(issue_text(n), "  | "))
    print("-" * 80)
    print("RESOLUTION:", resolutions().get(n, "(still open)"))
    print("=" * 80)
    calls = 0
    for l in lines:
        t = l["type"]
        if t == "plan":
            steps = (l.get("plan") or {}).get("steps") or []
            print(f"[plan v{l.get('version')}]")
            for s in steps:
                print(f"   step {s.get('id')}: {s.get('tool')} {s.get('args_json', '')}  -- {s.get('action', '')}")
        elif t == "model_call":
            text = (l.get("text") or "").strip()
            if text:
                print(f"[model {l.get('purpose') or ''} step {l.get('step')}] says:")
                print(indent(clip(text, args.full)))
        elif t == "tool_call":
            calls += 1
            err = "  ERROR" if l.get("is_error") else ""
            print(f"#{calls} {l['name']}({json.dumps(l.get('input'), ensure_ascii=False)}){err}"
                  + (f"   plan_step={l.get('plan_step')}" if l.get("plan_step") is not None else ""))
            result = l.get("result", l.get("result_excerpt", ""))
            print(indent(clip(result, args.full)))
        elif t == "end":
            print(f"[end] {l.get('terminal_reason')}: {l.get('detail')}")
        elif t == "run_end":
            tot = l.get("totals") or {}
            print(f"[run_end] {l.get('elapsed_s')} s, {tot.get('total_tokens')} tokens, ${tot.get('cost_usd')}")
        elif t not in ("run_start",):
            print(f"[{t}] " + clip(json.dumps({k: v for k, v in l.items() if k not in ('run_id', 't', 'type')},
                                             ensure_ascii=False), False, 300))
    print("=" * 80)
    st = json.loads(state_path(path).read_text())
    for issue, part in st["state"].items():
        print(f"END STATE on #{issue}: {short_state(part)}")
        for i, body in enumerate(part.get("comments", []), 1):
            print(f"  comment {i}:")
            print(indent(body, "    | "))
        for i, pr in enumerate(part.get("prs", []), 1):
            print(f"  pr {i}: {pr.get('title')}")
            print(indent(clip(pr.get("body", ""), args.full, 300), "    | "))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    r = sub.add_parser("run")
    r.add_argument("run_id")
    r.add_argument("--full", action="store_true")
    r.set_defaults(fn=cmd_run)
    i = sub.add_parser("issue")
    i.add_argument("number")
    i.set_defaults(fn=cmd_issue)
    args = p.parse_args(argv)
    args.fn(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
