"""Part C's arm A for claim 2 (Lecture 2, "the plan reduced repeated steps"): RepoMind's
planned way, ways/planned.py, with the two gpt-4.1-mini fixes my own Assignment 5
planned way carried, and nothing else.

Why this arm exists. The starter's planned way is the course's Assignment 5 solution;
mine, on gpt-4.1-mini, had two more fixes, and without them the starter's way rarely
reaches the steps the claim is about:

1. The planner prompt. The starter's prompts/planner.md lets gpt-4.1-mini add a step
   with no tool ("draft the comment"); agent/validator.py's check 3 rejects it, and
   after three rejected plans the run escalates having made no tool call. In four smoke
   runs outside the subset (g02, g07, g16, g23), three ended that way. My Assignment 5
   prompt has three more lines forbidding such a step: prompts/planner_a5.md (none of my
   54 Assignment 5 planned runs on gpt-4.1-mini failed planning).

2. Templates in a plan's arguments. gpt-4.1-mini often writes the comment step's body as
   a template, "label: $fill\\nfile: $fill\\n\\n$fill" (31 of my 54 Assignment 5 planned
   runs). The starter's executor fills only a value that starts with "$fill", so the
   template is sent as written, the label drawn from it is "$fill", and the registry
   and the policy hook refuse both writes (3 of 4 smoke runs with fix 1 alone). My
   Assignment 5 executor treats a value with "$fill" anywhere in it as not filled yet.
   ArmExecutor below is the starter's Executor with exactly that change, in `filled`
   and `fill` (three conditions: startswith(FILL) becomes FILL in ...).

Measured with the starter's way, arm A's repeats would be 0 mostly because its runs
make no call at all, which says nothing about whether a plan prevents repeated steps.
The validator, the reviser, the registry, the policy hook, the checkpoints and the
tools are the planned way's own; nothing outside this file and prompts/planner_a5.md
is edited.
"""

from __future__ import annotations

import agent.plan as plan
import ways.planned as planned
from harness.formats import FILL, format_triage_comment, parse_triage_comment

ARM_PLANNER_PROMPT = "prompts/planner_a5.md"


class ArmExecutor(planned.Executor):
    """The starter's Executor; a value with "$fill" anywhere in it is not filled yet."""

    def filled(self, step: dict, args: dict) -> dict | None:
        to_fill = [k for k, v in args.items() if FILL in str(v)]          # starter: str(v).startswith(FILL)
        if not to_fill:
            return args
        filled = self.fill(step, args, to_fill)
        if filled is None:
            self.record(step, args, None, "off_plan")
            self.ctx.trace.end("escalated", detail=f"step {step.get('id')}: no on-plan call in {planned.MAX_FILL_TRIES} tries")
        return filled

    def fill(self, step: dict, args: dict, keys: list[str], *, system: str = "executor.md",
             purpose: str = "execute", note: str = "") -> dict | None:
        schema = next((t for t in self.ctx.tools.schemas if t["name"] == step["tool"]), None)
        if schema is None:
            return None
        fixed = {k: v for k, v in args.items() if FILL not in str(v)}      # starter: not str(v).startswith(FILL)
        props = (schema.get("input_schema") or {}).get("properties") or {}
        nullable = {k for k, s in props.items() if isinstance(s, dict) and planned.allows_null(s)}
        for _ in range(planned.MAX_FILL_TRIES):
            self.calls += 1
            response = self.ctx.client.create(system=self.ctx.prompt(system), tools=[schema],
                                              messages=[{"role": "user", "content": self.fill_request(step, fixed, keys, note)}])
            self.ctx.trace.model_call(self.calls, response, purpose=purpose)
            for call in response.tool_calls:
                if call.name != step["tool"]:
                    self.refuse(step, call)
                    continue
                filled = {**{k: v for k, v in call.input.items() if k in props}, **fixed}
                if any(k not in filled or filled[k] == "" or FILL in str(filled[k])   # starter: startswith
                       or (filled[k] is None and k not in nullable)
                       for k in keys):
                    continue
                if planned.role(step["tool"]) == "comment":
                    body = planned.arg("comment", "body")
                    label, file = parse_triage_comment(str(filled[body]))
                    filled[body] = format_triage_comment(label or "bug", file, self.disclosure)
                return filled
        return None


def install() -> None:
    plan.PLANNER_PROMPT = ARM_PLANNER_PROMPT        # read at call time by agent.plan.make_plan
    planned.Executor = ArmExecutor                   # planned.run builds its executor by this name


def run(ctx) -> None:
    install()
    planned.run(ctx)


install()
