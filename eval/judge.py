"""Assignment 7, Part D: the judge, its rates and its correction (checks/FORMATS.md,
section 15.10).

    python -m eval.judge tune          # examples + tuning sets only: rates and misses (never the test set)
    python -m eval.judge test 1        # run 1 on the test set: eval/judge/verdicts/test_1.jsonl
    python -m eval.judge versions      # the test items' list and long versions: versions.jsonl
    python -m eval.judge recorded      # the agent way's recorded comments: recorded.jsonl
    python -m eval.judge score         # every number, for_a_person.txt, and LAB_07.json's judge block
    ... --backend harness.scripted:PassEverything     # the plumbing, for nothing (a coin)

The judge reads one output: its issue, what RepoMind's tools returned, in order, and
the comment; and answers with slide 36's fixed reply, JSON with a one-line "reasoning"
and then an "answer", "Pass" or "Fail". Its system prompt is prompts/judge.md with
eval/judge/criterion.md and the examples it names put in place (`system_prompt`); every
verdict line carries that prompt's digest, so a changed judge shows. Every call goes
through a metered judge session (harness.meter.judge_session), so its tokens and cost
are recorded, priced and counted against lab_token_ceiling.

The checker calls `correct`, `rates` and `bootstrap` on cases of its own, and
`correct` on a coin, so their names, arguments and returns stay as the stub gave them.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import sys
from pathlib import Path

import yaml

from harness import ROOT
from harness.meter import judge_session

OUTPUTS = ROOT / "fixtures" / "judge" / "outputs"
VERDICTS = ROOT / "eval" / "judge" / "verdicts"
PROMPT = ROOT / "prompts" / "judge.md"
CRITERION = ROOT / "eval" / "judge" / "criterion.md"
LABELS = ROOT / "eval" / "labels" / "labels.csv"
SPLIT = ROOT / "eval" / "labels" / "split.yaml"
TRACES = ROOT / "fixtures" / "traces7"
POOL = ROOT / "fixtures" / "issues" / "pool"
TUNING = ROOT / "eval" / "judge" / "tuning"
COMMENT_WRITES = ("issues_comment", "post_comment")
TRIES = 3                                   # a reply that is not the fixed JSON is asked for again


class CoinJudge(ValueError):
    """TPR + TNR is within 0.1 of 1: the judge is no better than a coin. Fix it, do not
    correct it (slide 44)."""


# -- the maths: rates, correction, interval ---------------------------------------------------

def correct(p: float, tpr: float, tnr: float) -> float:
    """The share you would pass, labelling by hand, from the judge's pass rate p on
    outputs nobody labelled: (p + TNR - 1) / (TPR + TNR - 1) (slide 44), clipped to
    0 to 1. Raises CoinJudge when TPR + TNR is within 0.1 of 1."""
    youden = tpr + tnr - 1
    if abs(youden) <= 0.1:
        raise CoinJudge(f"TPR + TNR = {tpr + tnr:.3f}, within 0.1 of 1: the judge is no better than a coin; "
                        "fix it, do not correct it")
    return min(1.0, max(0.0, (p + tnr - 1) / youden))


def rates(verdicts: dict[str, str], labels: dict[str, str]) -> tuple[float, float]:
    """(TPR, TNR) of the judge's verdicts against your labels, each "pass" or "fail",
    on the items both cover (slide 43): TPR is the share of the labelled passes the
    judge passed, TNR the share of the labelled fails it failed."""
    passes = [i for i, lab in labels.items() if lab == "pass" and i in verdicts]
    fails = [i for i, lab in labels.items() if lab == "fail" and i in verdicts]
    tpr = sum(verdicts[i] == "pass" for i in passes) / len(passes) if passes else 0.0
    tnr = sum(verdicts[i] == "fail" for i in fails) / len(fails) if fails else 0.0
    return tpr, tnr


def bootstrap(verdicts: dict[str, str], labels: dict[str, str], p: float,
              resamples: int = 2000, seed: int = 0) -> tuple[float, float]:
    """The middle 95% of the corrected rate over resamples of the test items, drawn
    with replacement, as many as there are, each time recomputing TPR and TNR
    (slide 44). A resample on which the judge is a coin is left out."""
    items = [i for i in labels if i in verdicts]
    rng = random.Random(seed)
    got = []
    for _ in range(resamples):
        draw = [rng.choice(items) for _ in items]
        n_pass = sum(labels[i] == "pass" for i in draw)
        n_fail = len(draw) - n_pass
        if not n_pass or not n_fail:                      # no TPR or no TNR on this resample
            continue
        tpr = sum(labels[i] == "pass" and verdicts[i] == "pass" for i in draw) / n_pass
        tnr = sum(labels[i] == "fail" and verdicts[i] == "fail" for i in draw) / n_fail
        try:
            got.append(correct(p, tpr, tnr))
        except CoinJudge:
            continue
    if not got:
        return (None, None)
    got.sort()
    return got[int(0.025 * (len(got) - 1))], got[int(0.975 * (len(got) - 1))]


# -- what the judge reads --------------------------------------------------------------------

def load_outputs(root: Path = ROOT) -> dict[str, dict]:
    """The 60 outputs to label, by ID (section 15.9)."""
    return {p.stem: json.loads(p.read_text()) for p in sorted((root / "fixtures" / "judge" / "outputs").glob("*.json"))}


def load_labels() -> dict[str, dict]:
    with LABELS.open(newline="") as f:
        return {r["id"].strip(): {"label": r["label"].strip().lower(), "reason": r["reason"].strip()}
                for r in csv.DictReader(f)}


def load_split() -> dict[str, list[str]]:
    data = yaml.safe_load(SPLIT.read_text())
    return {k: list(data[k]) for k in ("examples", "tuning", "test")}


def render(issue: dict, evidence: list[dict], comment: str) -> str:
    """One output as the judge reads it: the issue, every tool call in order with its
    whole result, then the comment. Nothing else: not the system that wrote it."""
    parts = ["COMMENT TO JUDGE", comment.strip(), "",
             f"ISSUE #{issue.get('number')}: {issue.get('title')}", str(issue.get("body") or "").strip(), "",
             f"TOOL RESULTS ({len(evidence)} calls, in the order the run made them)"]
    for k, e in enumerate(evidence, 1):
        parts.append(f"--- [{k}] {e.get('tool')}({json.dumps(e.get('input'), ensure_ascii=False)})")
        parts.append(str(e.get("result") or "").rstrip())
    parts += ["", "END OF TOOL RESULTS"]
    return "\n".join(parts)


REMINDER = ("Judge the COMMENT TO JUDGE above by the criterion: give each detail its source, "
            "[issue], a result number whose text states it, [none] or [contradicted by N]; "
            "any [none] or [contradicted ...] is Fail. Reply with the JSON only.")


def system_prompt() -> str:
    """prompts/judge.md with the criterion and the examples it names put in place."""
    text = PROMPT.read_text()
    header = re.search(r"^<!--\s*examples:\s*(.+?)\s*-->\s*$", text, re.M)
    ids = header.group(1).split() if header else []
    body = text[header.end():].lstrip("\n") if header else text
    outputs, labels, split = load_outputs(), load_labels(), load_split()
    blocks = []
    for k, oid in enumerate(ids, 1):
        if oid not in split["examples"]:
            raise SystemExit(f"prompts/judge.md: example {oid} is not in the examples set")
        o, lab = outputs[oid], labels[oid]
        blocks.append(f"### Example {k}: a clear {lab['label']}\n\n<output>\n"
                      f"{render(o['issue'], o['evidence'], o['comment'])}\n</output>\n\n"
                      f"The person's label: {lab['label'].capitalize()}. Their reason: {lab['reason']}")
    criterion = CRITERION.read_text().strip()
    return body.replace("{{criterion}}", criterion).replace("{{examples}}", "\n\n".join(blocks)).strip() + "\n"


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def parse(text: str) -> tuple[str, str] | None:
    """The fixed reply: JSON with "reasoning", then "answer" Pass or Fail. None if not."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        reply = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    answer = str(reply.get("answer", "")).strip().lower()
    if answer not in ("pass", "fail"):
        return None
    return answer, " ".join(str(reply.get("reasoning", "")).split())


def ask(session, system: str, text: str) -> tuple[str, str]:
    for _ in range(TRIES):
        response = session.client.create(system=system, messages=[{"role": "user", "content": f"{text}\n\n{REMINDER}"}])
        session.trace.model_call(0, response, purpose="judge")
        got = parse(response.text)
        if got:
            return got
    raise RuntimeError(f"no fixed reply in {TRIES} tries: {response.text[:200]!r}")


def judge_all(name: str, items: list[tuple[dict, str]], out: Path | None, backend: str | None) -> list[dict]:
    """Judge each (extra fields, text to read) in one metered session; write one line each."""
    system = system_prompt()
    lines = []
    with judge_session(name, backend) as session:
        for extra, text in items:
            answer, reasoning = ask(session, system, text)
            line = {**extra, "answer": answer, "reasoning": reasoning, "session": session.id,
                    "model": session.model, "prompt": digest(system)}
            lines.append(line)
            print(f"  {line['id']:<34} {line.get('version', ''):5} {answer:4}  {reasoning[:90]}", flush=True)
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("".join(json.dumps(x) + "\n" for x in lines))
        print(f"wrote {len(lines)} verdicts to {out.relative_to(ROOT)}; session {lines[0]['session'] if lines else '-'}")
    return lines


# -- the recorded runs (task 5) ---------------------------------------------------------------

def pool_issue(number: int) -> dict:
    raw = (POOL / f"{number}.md").read_text()
    _, front, body = raw.split("---", 2)
    meta = yaml.safe_load(front)
    body = re.sub(r"<!--\s*sentinel:.*?-->", "", body).strip()      # the fixtures' outputs leave it out too
    return {"number": meta.get("number", number), "title": meta.get("title"), "body": body}


def recorded() -> list[tuple[str, dict, list[dict], str]]:
    """(run ID, issue, evidence before the last comment, the last comment) for every
    recorded run of the agent way in fixtures/traces7/ that posted one."""
    out = []
    for path in sorted(TRACES.glob("*.jsonl")):
        if path.name.startswith("s27"):
            continue
        lines = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
        if not lines or lines[0].get("way") != "agent":
            continue
        calls = [x for x in lines if x.get("type") == "tool_call"]
        posted = [k for k, c in enumerate(calls) if c.get("name") in COMMENT_WRITES and not c.get("is_error")]
        if not posted:
            continue
        last = posted[-1]
        comment = str((calls[last].get("input") or {}).get("body") or "")
        evidence = [{"tool": c.get("name"), "input": c.get("input"), "result": c.get("result")} for c in calls[:last]]
        out.append((lines[0].get("run_id") or path.stem, pool_issue(int(lines[0]["issue"])), evidence, comment))
    return out


# -- the commands -----------------------------------------------------------------------------

def read_verdicts(name: str) -> list[dict]:
    path = VERDICTS / f"{name}.jsonl"
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []


def cmd_tune(backend: str | None) -> int:
    """Examples and tuning sets only. The test set's labels are never read here."""
    outputs, labels, split = load_outputs(), load_labels(), load_split()
    ids = split["examples"] + split["tuning"]
    items = [({"id": i}, render(outputs[i]["issue"], outputs[i]["evidence"], outputs[i]["comment"])) for i in ids]
    TUNING.mkdir(parents=True, exist_ok=True)
    n = len(list(TUNING.glob("round_*.jsonl"))) + 1
    lines = judge_all(f"tune-{n}", items, TUNING / f"round_{n}.jsonl", backend)
    v = {x["id"]: x["answer"] for x in lines}
    for name, part in (("examples", split["examples"]), ("tuning", split["tuning"])):
        tpr, tnr = rates(v, {i: labels[i]["label"] for i in part})
        print(f"{name:9} TPR {tpr:.3f}  TNR {tnr:.3f}")
    for x in lines:
        if x["answer"] != labels[x["id"]]["label"]:
            print(f"  miss {x['id']}: judge {x['answer']}, label {labels[x['id']]['label']} ({labels[x['id']]['reason']})"
                  f"\n       judge said: {x['reasoning']}")
    return 0


def cmd_test(k: int, backend: str | None) -> int:
    outputs, split = load_outputs(), load_split()
    items = [({"id": i}, render(outputs[i]["issue"], outputs[i]["evidence"], outputs[i]["comment"]))
             for i in split["test"]]
    judge_all(f"test-{k}", items, VERDICTS / f"test_{k}.jsonl", backend)
    print("(no rates here: `python -m eval.judge score` once every verdict file is written)")
    return 0


def cmd_versions(backend: str | None) -> int:
    outputs, split = load_outputs(), load_split()
    items = [({"id": i, "version": v}, render(outputs[i]["issue"], outputs[i]["evidence"], outputs[i]["versions"][v]))
             for i in split["test"] for v in ("list", "long")]
    judge_all("versions", items, VERDICTS / "versions.jsonl", backend)
    return 0


def cmd_recorded(backend: str | None) -> int:
    items = [({"id": rid}, render(issue, ev, comment)) for rid, issue, ev, comment in recorded()]
    judge_all("recorded", items, VERDICTS / "recorded.jsonl", backend)
    return 0


def cmd_score(write: bool) -> int:
    outputs, labels, split = load_outputs(), load_labels(), load_split()
    test = split["test"]
    on_test = {i: labels[i]["label"] for i in test}
    runs = [{x["id"]: x["answer"] for x in read_verdicts(f"test_{k}")} for k in (1, 2, 3)]
    if not all(sorted(r) == sorted(test) for r in runs):
        raise SystemExit("test_1, test_2 and test_3 must each judge exactly the test set")
    models = {x["model"] for k in (1, 2, 3) for x in read_verdicts(f"test_{k}")}
    prompts = {x.get("prompt") for k in (1, 2, 3) for x in read_verdicts(f"test_{k}")}
    v1 = runs[0]
    tpr, tnr = rates(v1, on_test)
    rec = read_verdicts("recorded")
    p = sum(x["answer"] == "pass" for x in rec) / len(rec) if rec else None
    try:
        corrected = correct(p, tpr, tnr) if p is not None else None
        coin = False
        lo, hi = bootstrap(v1, on_test, p) if p is not None else (None, None)
    except CoinJudge as exc:
        print(f"REFUSED: {exc}")
        corrected, coin, lo, hi = None, True, None, None
    flips = [i for i in test if len({r[i] for r in runs}) > 1]
    maj = {i: "pass" if sum(r[i] == "pass" for r in runs) >= 2 else "fail" for i in test}
    m_tpr, m_tnr = rates(maj, on_test)
    one = [rates(r, on_test) for r in runs]
    kept = (m_tpr + m_tnr) > (tpr + tnr)                   # balanced accuracy, against run 1
    versions = read_verdicts("versions")
    moved = sorted({x["id"] for x in versions if x["answer"] != v1[x["id"]]})
    by_system = {}
    for system in sorted({o["system"] for o in outputs.values()}):
        mine = {i: lab for i, lab in on_test.items() if outputs[i]["system"] == system}
        s_tpr, s_tnr = rates(v1, mine)
        by_system[system] = {"tpr": s_tpr, "tnr": s_tnr,
                             "passes": sum(x == "pass" for x in mine.values()),
                             "fails": sum(x == "fail" for x in mine.values())}

    n_pass, n_fail = sum(x == "pass" for x in on_test.values()), sum(x == "fail" for x in on_test.values())
    print(f"judge: {', '.join(sorted(models))}; prompt {', '.join(sorted(map(str, prompts)))}")
    print(f"test set: {len(test)} items, {n_pass} labelled pass, {n_fail} labelled fail")
    for k, (a, b) in enumerate(one, 1):
        print(f"  run {k}: TPR {a:.3f}  TNR {b:.3f}")
    print(f"  majority of 3: TPR {m_tpr:.3f}  TNR {m_tnr:.3f}  -> kept: {kept}")
    print(f"recorded: {len(rec)} comments, p = {p if p is None else round(p, 3)}")
    print(f"corrected {corrected if corrected is None else round(corrected, 3)}; 95% interval "
          f"[{lo if lo is None else round(lo, 3)}, {hi if hi is None else round(hi, 3)}]; coin {coin}")
    print(f"flip rate {len(flips)}/{len(test)} = {len(flips) / len(test):.3f}: {' '.join(flips) or '-'}")
    print(f"formatting/length: {len(moved)}/{len(test)} moved = {len(moved) / len(test):.3f}: {' '.join(moved) or '-'}")
    for x in versions:
        if x["answer"] != v1[x["id"]]:
            print(f"  {x['id']} {x['version']}: {v1[x['id']]} -> {x['answer']}")
    for s, r in by_system.items():
        print(f"  {s}: TPR {r['tpr']:.3f} (of {r['passes']} passes)  TNR {r['tnr']:.3f} (of {r['fails']} fails)")

    if write:
        (ROOT / "eval" / "judge" / "for_a_person.txt").write_text("".join(f"{i}\n" for i in flips))
        path = ROOT / "reports" / "LAB_07.json"
        report = json.loads(path.read_text())
        report["judge"] = {"split": {k: len(v) for k, v in split.items()},
                           "model": sorted(models)[0] if len(models) == 1 else sorted(models),
                           "tpr": tpr, "tnr": tnr, "p": p, "corrected": corrected,
                           "interval": [lo, hi] if lo is not None else None, "coin": coin,
                           "flip_rate": len(flips) / len(test),
                           "majority": {"tpr": m_tpr, "tnr": m_tnr, "kept": kept},
                           "moved_share": len(moved) / len(test),
                           "by_system": {s: {"tpr": r["tpr"], "tnr": r["tnr"]} for s, r in by_system.items()}}
        path.write_text(json.dumps(report, indent=2) + "\n")
        print("wrote eval/judge/for_a_person.txt and the judge block of reports/LAB_07.json")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["tune", "test", "versions", "recorded", "score", "prompt"])
    p.add_argument("run", nargs="?", type=int)
    p.add_argument("--backend", default=None, help="e.g. harness.scripted:PassEverything, to test the plumbing")
    p.add_argument("--dry-run", action="store_true", help="score: print only")
    args = p.parse_args(argv)
    if args.command == "prompt":
        text = system_prompt()
        sys.stdout.write(text)
        print(f"\n[prompt {digest(text)}, {len(text)} characters]", file=sys.stderr)
        return 0
    if args.command == "tune":
        return cmd_tune(args.backend)
    if args.command == "test":
        if args.run not in (1, 2, 3):
            raise SystemExit("test takes the run number, 1, 2 or 3")
        return cmd_test(args.run, args.backend)
    if args.command == "versions":
        return cmd_versions(args.backend)
    if args.command == "recorded":
        return cmd_recorded(args.backend)
    return cmd_score(not args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
