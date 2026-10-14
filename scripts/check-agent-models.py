#!/usr/bin/env python3
"""
Lint: every agent in ~/.claude/agents/*.md must declare a valid model tier AND an explicit
tool grant in its frontmatter. Roster-agnostic — unlike the retired assign-agent-models.py it
hardcodes NO agent names, so it never breaks when the roster changes (add / remove / rename an
agent freely). The policy itself lives in each agent's frontmatter (the source of truth); this
only guards against drift: a missing line, a typo, an unknown tier, or an agent that quietly
inherits every tool because nobody wrote `tools`.

The tool half was added 2026-08-27. Isolation is the point of an agent, and an agent with no
`tools` has the widest possible grant while looking like every other entry in the
roster. Three agents were in that state, one of them harness-director: the agent that edits the
orchestration layer had the least constrained harness of any agent in the corpus, and no check
reported it because this script only looked at models. That is also why it now has a --hook
mode; before that it reported to nobody, being wired to nothing.

Until 2026-10-06 it checked `allowed-tools:`, a key Claude Code honours only in SKILL frontmatter.
For subagents it is silently ignored, so all agents passed this lint while inheriting every tool
(probed both through `claude -p --agent` and the Agent tool). The subagent key is `tools:`; it
takes tool names and MCP server patterns (`mcp__<server>`), not permission specifiers, so
`Bash(cmd:*)` there narrows nothing. A leftover `allowed-tools:` and a specifier inside `tools:`
are both violations now; an agent that needs one command holds `Bash` and narrows it with an
agent-scoped PreToolUse hook (hooks/agent-bash-guard.py).

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

import yaml

AGENTS_DIR = Path(os.path.expanduser("~/.claude/agents"))
VALID_MODELS = ("opus", "sonnet", "haiku")

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
# `tools:` takes names and MCP server patterns; `Bash(cmd:*)` grants or removes the whole tool.
# `Agent(type, ...)` is the one documented exception (an allowlist under `claude --agent`).
SPECIFIER_RE = re.compile(r"^(?!Agent\(|Task\()[A-Za-z]+\(.*\)$")
# An agent may legitimately need an open tool surface — post-deploy-qa drives live verification
# through whatever MCP the project provides, and enumerating those names would couple it to the
# MCP roster. Such an agent declares `tools-unrestricted:` with a reason (and may still narrow
# with `disallowedTools:`). The point of the check is that no agent is unrestricted SILENTLY, not
# that none ever is.
#
# Frontmatter is parsed as YAML, not matched line by line. The regex version this replaced read a
# YAML list as the inline value "- Read" (`\s*` crossed the newline), let quotes and trailing
# comments hide a `Bash(...)` specifier, and accepted an empty `tools-unrestricted:`.


def frontmatter(content: str) -> tuple[dict | None, str | None]:
    """Return (mapping, error) for the agent file's YAML frontmatter."""
    fm = FRONTMATTER_RE.match(content.replace("\r\n", "\n"))
    if not fm:
        return None, "no frontmatter"
    try:
        data = yaml.safe_load(fm.group(1))
    except yaml.YAMLError as e:
        return None, f"frontmatter is not valid YAML ({str(e).splitlines()[0]})"
    if not isinstance(data, dict):
        return None, "frontmatter is not a mapping"
    return data, None


def split_tools(value: str) -> list[str]:
    """Split a comma string at top level only: `Agent(a, b)` stays one entry."""
    out, cur, depth = [], "", 0
    for ch in value:
        depth += (ch == "(") - (ch == ")")
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return [t.strip() for t in out if t.strip()]


def tools_of(content: str) -> tuple[list[str] | None, str | None]:
    """Return (tools, error). error is None when the grant is explicit, or when an open surface
    is declared with a reason. `["*"]` marks a declared exception."""
    data, err = frontmatter(content)
    if err:
        return None, err
    if "allowed-tools" in data:
        return None, "allowed-tools: is ignored for agents (skills-only key); rename it to tools:"
    if "tools-unrestricted" in data:
        reason = data["tools-unrestricted"]
        if not isinstance(reason, str) or not reason.strip():
            return None, "tools-unrestricted: needs a written reason"
        return ["*"], None
    if "tools" not in data:
        return None, "no tools: line (inherits every tool)"
    value = data["tools"]
    if isinstance(value, str):
        tools = split_tools(value)
    elif isinstance(value, list) and all(isinstance(t, str) for t in value):
        tools = [t.strip() for t in value if t.strip()]
    elif value is None:
        tools = []
    else:
        return None, "tools: must be a comma string or a list of tool names"
    if not tools:
        return None, "tools: is empty (inherits every tool)"
    spec = [t for t in tools if SPECIFIER_RE.match(t)]
    if spec:
        return None, (f"tools: entry {spec[0]!r} has a specifier, which tools: does not honour "
                      "(it grants the whole tool); list the bare tool and narrow it with a hook")
    return tools, None


def model_of(content: str) -> tuple[str | None, str | None]:
    """Return (model, error). error is None when a valid model line is present."""
    data, err = frontmatter(content)
    if err:
        return None, err
    if "model" not in data:
        return None, "no model: line"
    val = str(data["model"]).strip()
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
