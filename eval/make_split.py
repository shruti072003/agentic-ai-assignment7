"""Part D, task 3: split the 60 labelled outputs into examples, tuning and test, never mixed
(slide 42; checks/FORMATS.md, section 15.9). Spends nothing.

    python -m eval.make_split            # writes eval/labels/split.yaml (seed 7)

Random but balanced: the outputs are grouped by (system, label), each group is shuffled
with a fixed seed, and its items are dealt into the three sets in proportion, so every
set holds both systems and both labels. Sizes: 8 examples (13%), 26 tuning (43%), 26 test
(43%). The test set is held out: nothing about the judge is tuned on it.
"""

from __future__ import annotations

import csv
import json
import random
from collections import defaultdict

import yaml

from harness import ROOT

SEED = 7
SIZES = {"examples": 8, "tuning": 26, "test": 26}


def main() -> int:
    with (ROOT / "eval" / "labels" / "labels.csv").open() as f:
        labels = {r["id"]: r["label"] for r in csv.DictReader(f)}
    system = {p.stem: json.loads(p.read_text())["system"]
              for p in sorted((ROOT / "fixtures" / "judge" / "outputs").glob("*.json"))}
    groups = defaultdict(list)
    for oid in sorted(labels):
        groups[(system[oid], labels[oid])].append(oid)
    rng = random.Random(SEED)
    order = []
    for key in sorted(groups):
        items = groups[key][:]
        rng.shuffle(items)
        order.extend(items)
    # Deal the stratified order round-robin by quota, so each set gets a share of every group.
    out = {k: [] for k in SIZES}
    total = sum(SIZES.values())
    for i, oid in enumerate(order):
        # the set whose share so far lags its target most takes the next item
        name = max(SIZES, key=lambda k: SIZES[k] * (i + 1) / total - len(out[k]))
        out[name].append(oid)
    out = {k: sorted(v) for k, v in out.items()}
    (ROOT / "eval" / "labels" / "split.yaml").write_text(
        f"# Part D, task 3: seeded ({SEED}), balanced by system and label; eval/make_split.py\n"
        + yaml.safe_dump(out, default_flow_style=None, sort_keys=False, width=100))
    for k, v in out.items():
        counts = defaultdict(int)
        for oid in v:
            counts[(system[oid].replace("claude-", ""), labels[oid])] += 1
        print(f"{k:9} {len(v):2}  {dict(sorted(counts.items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
