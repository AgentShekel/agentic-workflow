#!/usr/bin/env python3
"""
Lint: every agent in ~/.claude/agents/*.md must declare a valid model tier AND an explicit
tool grant in its frontmatter. Roster-agnostic — unlike the retired assign-agent-models.py it
hardcodes NO agent names, so it never breaks when the roster changes (add / remove / rename an
agent freely). The policy itself lives in each agent's frontmatter (the source of truth); this
only guards against drift: a missing line, a typo, an unknown tier, or an agent that quietly
inherits every tool because nobody wrote `allowed-tools`.

The tool half was added 2026-08-27. Isolation is the point of an agent, and an agent with no
`allowed-tools` has the widest possible grant while looking like every other entry in the
roster. Three agents were in that state, one of them harness-director: the agent that edits the
orchestration layer had the least constrained harness of any agent in the corpus, and no check
reported it because this script only looked at models. That is also why it now has a --hook
mode; before that it reported to nobody, being wired to nothing.

Policy reference (categories, not a hardcoded list — see agents' frontmatter for the
authoritative per-agent assignment):
  opus   — top-level leads, per-engagement acceptor managers, system-optimizer directors,
           dev-tech-architect, and verdict-bearing critical validators (code-reviewer,
           security-auditor, skeptic, reality-checker, userspec-adequacy-validator)
  haiku  — mechanical / template-compliance validators
  sonnet — everything else (engineers, designers, analysts, researchers, and
           non-critical deep-reasoning validators)

Run:
  python ~/.claude/scripts/check-agent-models.py          # distribution + violations; exit 1 on any violation
  python ~/.claude/scripts/check-agent-models.py --quiet  # print only violations + exit code
  python ~/.claude/scripts/check-agent-models.py --hook   # silent when clean; always exit 0
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

AGENTS_DIR = Path(os.path.expanduser("~/.claude/agents"))
VALID_MODELS = ("opus", "sonnet", "haiku")

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
MODEL_LINE_RE = re.compile(r"^model:\s*(\S.*?)\s*$", re.MULTILINE)
TOOLS_LINE_RE = re.compile(r"^allowed-tools:\s*(.*)$", re.MULTILINE)
# An agent may legitimately need an open tool surface — post-deploy-qa drives live verification
# through whatever MCP the project provides, and enumerating those names would couple it to the
# MCP roster. Such an agent declares `tools-unrestricted:` with a reason. The point of the check
# is that no agent is unrestricted SILENTLY, not that none ever is.
UNRESTRICTED_RE = re.compile(r"^tools-unrestricted:\s*(\S.*)$", re.MULTILINE)


def tools_of(content: str) -> tuple[list[str] | None, str | None]:
    """Return (tools, error). error is None when the grant is explicit, or when an open surface
    is declared with a reason. `["*"]` marks a declared exception."""
    fm = FRONTMATTER_RE.match(content)
    if not fm:
        return None, "no frontmatter"
    body = fm.group(1)
    if UNRESTRICTED_RE.search(body):
        return ["*"], None
    m = TOOLS_LINE_RE.search(body)
    if not m:
        return None, "no allowed-tools: line (inherits every tool)"
    inline = m.group(1).strip()
    if inline:
        tools = [t.strip() for t in inline.strip("[]").split(",") if t.strip()]
    else:
        tools = []
        for line in body[m.end():].splitlines():
            if re.match(r"^\s+-\s+\S", line):
                tools.append(line.strip()[1:].strip())
            elif line.strip():
                break
    if not tools:
        return None, "allowed-tools: is empty (inherits every tool)"
    return tools, None


def model_of(content: str) -> tuple[str | None, str | None]:
    """Return (model, error). error is None when a valid model line is present."""
    fm = FRONTMATTER_RE.match(content)
    if not fm:
        return None, "no frontmatter"
    m = MODEL_LINE_RE.search(fm.group(1))
    if not m:
        return None, "no model: line"
    val = m.group(1).strip()
    if val not in VALID_MODELS:
        return val, f"invalid model {val!r} (want one of {list(VALID_MODELS)})"
    return val, None


def main() -> int:
    ap = argparse.ArgumentParser(description="Lint agent model frontmatter (roster-agnostic).")
    ap.add_argument("--quiet", action="store_true", help="print only violations")
    ap.add_argument("--hook", action="store_true",
                    help="silent when clean; always exit 0 (SessionStart hook mode)")
    args = ap.parse_args()

    files = sorted(AGENTS_DIR.glob("*.md"))
    if not files:
        if not args.hook:
            print(f"no agents found in {AGENTS_DIR}", file=sys.stderr)
        return 0 if args.hook else 2

    counts = {m: 0 for m in VALID_MODELS}
    violations: list[str] = []
    declared: list[str] = []

    for path in files:
        content = path.read_text(encoding="utf-8")
        model, err = model_of(content)
        if err:
            violations.append(f"{path.name}: {err}")
        else:
            counts[model] += 1
        tools, terr = tools_of(content)
        if terr:
            violations.append(f"{path.name}: {terr}")
        elif tools == ["*"]:
            declared.append(path.name)

    if args.hook:
        if violations:
            lines = ["Agent frontmatter drift. An agent without an explicit model or tool "
                     "grant silently loses its isolation; surface this to the user:"]
            lines += [f"- {v}" for v in violations]
            lines.append("Fix in ~/.claude/agents/<name>.md, then re-run "
                         "`python ~/.claude/scripts/check-agent-models.py`.")
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "SessionStart", "additionalContext": "\n".join(lines)}},
                ensure_ascii=False))
        return 0

    if not args.quiet:
        dist = " ".join(f"{m}={counts[m]}" for m in VALID_MODELS)
        print(f"agents: {len(files)}  ({dist})")
        print(f"tool grants: {len(files) - len(declared)}/{len(files)} explicit"
              + (f"; declared open surface: {', '.join(declared)}" if declared else ""))

    for v in violations:
        print(f"VIOLATION {v}")

    if violations:
        print(f"\n{len(violations)} violation(s)")
        return 1
    if not args.quiet:
        print("ok: every agent declares a valid model and an explicit tool grant")
    return 0


if __name__ == "__main__":
    sys.exit(main())
