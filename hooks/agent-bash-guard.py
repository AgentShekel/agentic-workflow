#!/usr/bin/env python3
"""PreToolUse guard for agents that hold Bash for one narrow purpose.

An agent's `tools:` frontmatter takes tool NAMES only. `Bash(python x.py:*)` there does not narrow
Bash to that command (Claude Code docs: a specifier still grants or removes the whole tool), so an
agent that needs a single command lists plain `Bash` in `tools:` and wires this guard as an
agent-scoped hook. Agent frontmatter hooks fire both on Agent-tool dispatch (engagement-workflow)
and on `claude --agent` (validator_lg.py); the headless path is narrowed a second time by its own
`--allowedTools`.

    hooks:
      PreToolUse:
        - matcher: "Bash"
          hooks:
            - type: command
              command: "python ~/.claude/hooks/agent-bash-guard.py contrast"

Profiles:
  contrast  `python|python3|py <contrast.py> ...` (accessibility-validator); the script path must be
            written exactly as one of CONTRAST_PATHS, unquoted.
  git-read  `git [-C <dir>] [--no-pager] diff|log|show|rev-parse|merge-base|ls-files|blame ...`
            (anti-pattern-detector)
            Residual risk: read-only git still runs the reviewed repo's own diff drivers,
            textconv filters and pager config from its .git/config, so a hostile repository
            could execute code through `git diff`/`log -p`. Acceptable only when every
            reviewed repo is your own; harden (e.g. `-c diff.external= --no-textconv`,
            GIT_CONFIG_NOSYSTEM, an isolated HOME) before reviewing third-party repositories.
  audit     `npm|pnpm|yarn audit` and `pip-audit --disable-pip`, each with an allowlist of options
            (security-auditor dependency scan; no fix, no output files, no registry/config swap)

The guard has to judge the words bash will actually execute, not a normalised guess of them, so
anything bash would rewrite is refused instead of interpreted: chaining, redirection, substitution,
backslash escapes, brace and history expansion, and unquoted glob characters. A quoted `~` stays
literal in bash, which is why the contrast path is compared as raw text. Every failure, malformed
input included, exits 2 (blocking); stderr is what the agent sees, so it says what is allowed.

Residual risk, accepted: a repository's own `.git/config` can still declare diff drivers or
textconv filters that `git diff/log/show` run. That config belongs to the repo owner whose code is
under review; this guard stops the agent from injecting such programs, not the owner.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Refused anywhere in the command: bash rewrites or chains on every one of these.
FORBIDDEN = set(";&|<>`$\\{}!\n\r")
# Refused outside quotes: pathname expansion would substitute words the guard never saw.
GLOB = set("*?[]")


def _home_forms() -> set[str]:
    home = Path.home().as_posix()                      # C:/Users/name
    forms = {home}
    if len(home) > 2 and home[1] == ":":
        forms.add(f"/{home[0].lower()}{home[2:]}")     # Git Bash /c/Users/name
    return forms


CONTRAST_PATHS = {"~/.claude/scripts/contrast.py"} | {f"{h}/.claude/scripts/contrast.py" for h in _home_forms()}
PYTHONS = {"python", "python3", "py"}
GIT_READ = {"diff", "log", "show", "rev-parse", "merge-base", "ls-files", "blame"}
# Long options that make a read-only git subcommand write a file or run a program.
GIT_BAD_LONG = ("--output", "--output-indicator-new", "--ext-diff", "--textconv", "--exec-path",
                "--upload-pack", "--open-files-in-pager")
AUDIT_NODE = {"npm", "pnpm", "yarn"}
# Audit options are allowlisted, not denylisted: npm resolves abbreviations (`--reg=` is
# `--registry=`), so a denylist of names can always be spelled around.
LEVELS = {"info", "low", "moderate", "high", "critical"}
NODE_FLAGS = {"--json", "--production", "--prod", "--dev", "--package-lock-only"}
NODE_VALUED: dict[str, set[str] | None] = {"--audit-level": LEVELS, "--level": LEVELS,
                                           "--omit": {"dev", "optional", "peer"},
                                           "--include": {"dev", "optional", "peer", "prod"}}
PIP_FLAGS = {"--disable-pip", "--no-deps", "--require-hashes", "--strict", "--desc", "--skip-editable",
             "--local", "-l"}
PIP_VALUED: dict[str, set[str] | None] = {"-r": None, "--requirement": None,
                                          "-f": {"json", "columns", "markdown"},
                                          "--format": {"json", "columns", "markdown"}}


def split_words(command: str) -> list[tuple[str, str]] | str:
    """Split into (raw, value) words the way bash would, for the subset this guard admits.
    Returns an error string for anything outside that subset."""
    bad = sorted(set(command) & FORBIDDEN)
    if bad:
        return f"one plain command only: refused character(s) {' '.join(repr(c) for c in bad)}"
    words, raw, val, quote, started = [], "", "", None, False
    for ch in command:
        if quote:
            if ch == quote:
                quote = None
            else:
                val += ch
            raw += ch
            continue
        if ch in "'\"":
            quote, started = ch, True
            raw += ch
            continue
        if ch in " \t":
            if started:
                words.append((raw, val))
            raw, val, started = "", "", False
            continue
        if ch in GLOB:
            return f"unquoted glob character {ch!r}: quote the pattern"
        if ch == "#" and not started:
            return "unquoted '#' starts a shell comment that drops the rest of the line: quote it"
        if ch == "~" and raw[-1:] in ("=", ":"):
            return "'~' after '=' or ':' is expanded by bash; spell the path out"
        raw += ch
        val += ch
        started = True
    if quote:
        return "unterminated quote"
    if started:
        words.append((raw, val))
    return words or "empty command"


def check_contrast(words: list[tuple[str, str]]) -> str | None:
    if len(words) < 2 or words[0][0] not in PYTHONS or words[1][0] not in CONTRAST_PATHS:
        return ("only `python ~/.claude/scripts/contrast.py <fg> <bg> [...]` may run "
                "(script path unquoted, exactly as written)")
    return None


def check_git_read(words: list[tuple[str, str]]) -> str | None:
    argv = [v for _, v in words]
    if argv[0] != "git":
        return "only read-only git commands may run"
    i = 1
    while i < len(argv) and argv[i] in ("-C", "--no-pager"):
        i += 2 if argv[i] == "-C" else 1
    if i >= len(argv) or argv[i] not in GIT_READ:
        return (f"git subcommand must be one of {sorted(GIT_READ)}; only -C <dir> and --no-pager may "
                "precede it (use `git -C <dir> ...`, not `cd`)")
    for a in argv[i + 1:]:
        name = a.split("=", 1)[0]
        # git accepts unambiguous abbreviations of long options (`--outp=` is `--output=`), so a
        # long option is refused when it is a prefix of a dangerous one, not only when it equals it.
        if a.startswith("--") and len(name) > 2 and any(b.startswith(name) for b in GIT_BAD_LONG):
            return f"option {a!r} writes a file or runs an external program"
    return None


def _allowlisted(args: list[str], flags: set[str], valued: dict[str, set[str] | None]) -> str | None:
    """Every arg must be an exact flag, `--opt=value` / `--opt value` for an allowlisted option, or
    (valued[opt] is None) a path-like value that is not itself an option. npm resolves abbreviated
    option names (`--reg` is `--registry`), so anything not spelled out here is refused."""
    i = 0
    while i < len(args):
        a = args[i]
        name, eq, value = a.partition("=")
        if a in flags:
            i += 1
            continue
        if name in valued:
            if not eq:
                if i + 1 >= len(args):
                    return f"option {a!r} needs a value"
                value, i = args[i + 1], i + 1
            allowed = valued[name]
            if (allowed is None and value.startswith("-")) or (allowed is not None and value not in allowed):
                return f"value {value!r} is not allowed for {name}"
            i += 1
            continue
        return f"option or argument {a!r} is not on the audit allowlist"
    return None


def check_audit(words: list[tuple[str, str]]) -> str | None:
    argv = [v for _, v in words]
    if argv[0] in AUDIT_NODE and len(argv) > 1 and argv[1] == "audit":
        return _allowlisted(argv[2:], NODE_FLAGS, NODE_VALUED)
    if argv[0] == "pip-audit":
        if "--disable-pip" not in argv:
            # Without it pip-audit resolves requirements through pip, which can run a package's
            # build backend: that is code execution chosen by whoever wrote the requirements.
            return "pip-audit needs --disable-pip (with --no-deps or a hashed requirements file)"
        return _allowlisted(argv[1:], PIP_FLAGS, PIP_VALUED)
    return "only `npm|pnpm|yarn audit` or `pip-audit --disable-pip` may run"


PROFILES = {"contrast": check_contrast, "git-read": check_git_read, "audit": check_audit}


def verdict(profile: str, command: object) -> str | None:
    """Return None to allow, else the reason the command is blocked."""
    if not isinstance(command, str):
        return "no command string in hook input"
    words = split_words(command.strip())
    if isinstance(words, str):
        return words
    return PROFILES[profile](words)


def decide(profile: str, stdin_text: str) -> str | None:
    data = json.loads(stdin_text)
    if not isinstance(data, dict):
        return "hook input is not an object"
    tool_name = data.get("tool_name", "Bash")
    if not isinstance(tool_name, str):
        return "hook input has no tool_name string"
    if tool_name != "Bash":
        return None
    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        return "hook input has no tool_input object"
    return verdict(profile, tool_input.get("command"))


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in PROFILES:
        print(f"agent-bash-guard: usage: agent-bash-guard.py {{{'|'.join(PROFILES)}}}", file=sys.stderr)
        return 2
    try:
        reason = decide(sys.argv[1], sys.stdin.read() or "{}")
    except Exception as e:  # noqa: BLE001 — any failure must block, never fall through as exit 1
        reason = f"guard failed on its input ({type(e).__name__}), blocking"
    if reason:
        print(f"Blocked by agent-bash-guard ({sys.argv[1]}): {reason}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
