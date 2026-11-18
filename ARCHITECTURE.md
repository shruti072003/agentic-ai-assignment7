# ARCHITECTURE.md · RepoMind on the seven layers

For each layer: what does this job, and where is it enforced. Cite code as a file
path and line number joined by a colon, inside backticks; a checker opens every
reference (`checks/FORMATS.md`, section 8). A layer held only by a sentence in a
prompt (any file under `prompts/`) is **EMPTY**, and so is a layer nothing does
yet. Status is one of: present, partial (say what is missing), or **EMPTY**. Each
assignment brings this file up to date.

What each layer is for (Lecture 1, slides 42 to 44):

- **Model**: reasoning, choosing tools, generating text.
- **Harness**: runs the loop, builds each prompt, trims old history.
- **Tools**: where the system acts on the world.
- **Memory & State**: what survives a step, a session, a restart.
- **Control & Policy**: what the system may do, and when it must ask.
- **Observability**: a step-by-step record of what it did.
- **Evaluation**: measuring quality, before and after release.

The table below is RepoMind as Assignment 7 leaves it: Assignment 5's working solution, with Assignment 7's evaluation layer.

| Layer | What does this job | Where it is enforced | Status |
|---|---|---|---|
| Model | The configured model, called only through the metered client | `harness/client.py:150` | present |
| Harness | The loop, with three bounds checked in code; a plan validated before it runs, and an executor that runs only the plan's steps; the client drains the user's messages before every call | `agent/loop.py:38`, `ways/planned.py:327`, `ways/planned.py:488`, `ways/planned.py:180` | present |
| Tools | Ten namespaced tools behind one registry: every call checked at the boundary before it runs; every write keyed by the harness, checked before each attempt and read back after a timeout; every attempt in the call record | `tools/__init__.py:170`, `tools/__init__.py:260`, `tools/__init__.py:269`, `tools/__init__.py:286`, `tools/__init__.py:325` | present |
| Memory & State | A checkpoint after each file read and before each write, sync, and a resume from the last one; a store of dated records with their origin, read before the first search and written once at the end of a run | `ways/planned.py:387`, `ways/planned.py:400`, `ways/planned.py:263`, `ways/planned.py:283`, `state/checkpointer.py:55`, `state/store.py:96` | present |
| Control & Policy | The autonomy policy in three columns, enforced by a pre-call hook outside the model: a stop first, prohibited before everything, a user's boundary kept as a rule, the disclosure line, and the reviewer asked for a gated call, with no answer never a yes; an escalation on a named signal that holds; a stop with a live notification; rollback by the remote's compensations | `tools/__init__.py:147`, `policy/hook.py:52`, `policy/hook.py:130`, `policy/hook.py:142`, `policy/hook.py:145`, `policy/hook.py:154`, `policy/hook.py:174`, `policy/boundary.py:33`, `ways/planned.py:209`, `ways/planned.py:460`, `ways/planned.py:546`, `policy/escalation.py:49`, `bin/rollback:24` | partial: the approvals still decay, as Lecture 5's Section B predicts, and nothing measures harm prevented |
| Observability | One trace line per model call and per tool call, and the plan as data before it runs; every refusal in the hook log, every decision in the decisions log, every write in the remote's log | `agent/loop.py:50`, `ways/planned.py:219`, `policy/hook.py:183` | partial: traces and logs, no alerts |
| Evaluation | A golden set of 28 tasks from RepoMind's own traces, in four strata, each with a decision and an expected end state; a grounded check that reads each run's end state in the tracker, fact by fact, never what the agent said; a harness that writes one result line per run with its pass, measure, facts, metrics and cost; pass@k, pass^k, spreads, intervals and sweep sizing; five trajectory metrics; a claim settled against a bar committed before its fourth sweep; a model judge validated against hand labels on a held-out test set, with its rate corrected, bootstrapped and refused for a coin | `eval/golden/v1/manifest.yaml:1`, `eval/grounded.py:98`, `eval/results_07.py:125`, `eval/results_07.py:144`, `eval/stats.py:21`, `eval/stats.py:32`, `eval/stats.py:71`, `eval/stats.py:82`, `eval/metrics.py:102`, `eval/thresholds/claim.yaml:16`, `eval/report_07.py:129`, `eval/judge.py:59`, `eval/judge.py:65`, `eval/judge.py:70`, `eval/judge.py:81`, `eval/judge.py:191` | partial: offline only, run by hand; the judge is weak (TPR 0.733, TNR 0.545) and its corrected rate on the recorded runs is uninformative ([0, 1]), so no grounding rate is reported from it |

**Empty layers: 0 of 7**, and three are partial.
