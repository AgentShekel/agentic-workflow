#!/usr/bin/env python3
"""Refuse git commands that skip git's own hooks; classify commit commands for the commit hooks.

Reads the PreToolUse payload on stdin (as UTF-8 bytes: without PYTHONUTF8 a Windows Python
decodes piped stdin with the ANSI code page, and a Cyrillic letter in the payload would make
the guard fail open).
  default      print a PreToolUse "deny" JSON when the Bash command bypasses git hooks, else nothing
  --classify   print {"commit": bool, "dirs": [...]}: whether any segment is a `git commit`, and
               the directory it runs in (`cd X &&` before it, then `-C`), relative to the cwd

Vectors:
`--no-verify` and its unambiguous prefixes on commit/push/pull/merge/am/cherry-pick/rebase/
revert; `-n` inside a `git commit` short-option cluster; core.hooksPath via `-c`,
`--config-env`, `git config` writes, GIT_CONFIG_* assignments (inline or `export`); aliases
that expand to a bypass; `bash|sh -c` / `-lc` and `eval` judged recursively; wrappers such as
`timeout 60` and `xargs`. Before tokenising, backslash-newline continuations are joined and
heredoc bodies are removed (a commit message or a doc that MENTIONS `--no-verify` is text).
Commands are split on newlines and separators and tokenised with shlex without comment
stripping. Only a `git` in command position counts.
Residual, accepted: `$(...)` / backtick substitution and variables that expand to `git`.
"""

import json
import os
import re
import shlex
import sys

SEPARATORS = {";", "&&", "||", "|", "&", "\n", "(", ")"}
SEPARATOR_CHARS = set(";&|\n()")
WRAPPERS = {"env", "command", "exec", "time", "nohup", "sudo", "builtin", "nice", "if", "then", "else",
            "elif", "do", "while", "until", "!", "{"}
WRAPPERS_WITH_ARG = {"timeout"}  # wrapper followed by options and one positional (the duration)
HOOKED = {"commit", "push", "pull", "merge", "am", "cherry-pick", "rebase", "revert"}
COMMIT_VALUE_OPTS = set("mFCct")  # value attached or in the next token
COMMIT_ATTACHED_ONLY = set("uS")  # optional value, attached only (-uno, -S<keyid>)
COMMIT_LONG_VALUE = {"--message", "--file", "--reuse-message", "--reedit-message", "--template",
                     "--author", "--date", "--fixup", "--squash", "--trailer", "--pathspec-from-file",
                     "--cleanup", "--untracked-files", "--gpg-sign"}
GLOBAL_VALUE = {"-c", "-C", "--git-dir", "--work-tree", "--namespace", "--config-env", "--exec-path",
                "--super-prefix", "--list-cmds"}
CONFIG_READS = {"--get", "--get-all", "--get-regexp", "--list", "-l", "--show-origin", "--show-scope",
                "get", "list", "--get-urlmatch"}
ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# Any word bash accepts as a delimiter, not only identifiers (`<<'END-MSG'`; Codex review 2026-10-14).
HEREDOC = re.compile(r"<<(-?)[ \t]*(['\"]?)([^\s'\"<>|&;()]+)\2")
BACKSLASH = chr(92)


def preprocess(cmd):
    """Join backslash-newline continuations; drop heredoc bodies (their text is data)."""
    cmd = cmd.replace(BACKSLASH + "\r\n", "").replace(BACKSLASH + "\n", "")
    out, pending = [], []
    for line in cmd.split("\n"):
        if pending:
            strip_tabs, word = pending[0]
            if (line.lstrip("\t") if strip_tabs else line).rstrip("\r") == word:
                pending.pop(0)
            continue
        out.append(line)
        pending = [(m.group(1) == "-", m.group(3)) for m in HEREDOC.finditer(line)]
    return "\n".join(out)


def segments(cmd):
    lex = shlex.shlex(cmd, posix=True, punctuation_chars="();<>|&\n")
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    lex.commenters = ""
    seg = []
    for tok in lex:
        if tok in SEPARATORS or (tok and set(tok) <= SEPARATOR_CHARS):
            if seg:
                yield seg
            seg = []
        else:
            seg.append(tok)
    if seg:
        yield seg


def safe_segments(cmd):
    """Segments up to the first tokenising error (unbalanced quote): what was read still counts."""
    out = []
    try:
        for seg in segments(preprocess(cmd)):
            out.append(seg)  # noqa: PERF402 -- list() would lose the segments read before a ValueError
    except ValueError:
        pass
    return out


def is_no_verify(tok):
    return tok.startswith("--no-v") and "--no-verify".startswith(tok.split("=")[0])


def alias_bypasses(expansion):
    """An alias expansion (`commit -n`, `!git -c core.hooksPath=x commit`) that bypasses hooks."""
    shell = expansion.startswith("!")
    try:
        words = shlex.split(expansion.lstrip("!"))
    except ValueError:
        return False
    if not words:
        return False
    if shell or git_name(words[0]):
        return judge_command(expansion.lstrip("!") if shell else " ".join(shlex.quote(w) for w in words)) is not None
    return judge_git_args(words) is not None


def commit_cluster_has_n(tok):
    """(has -n, value is in the next token) for a short-option cluster of `git commit`."""
    for k, ch in enumerate(tok[1:]):
        if ch == "n":
            return True, False
        if ch in COMMIT_VALUE_OPTS:
            return False, k == len(tok) - 2
        if ch in COMMIT_ATTACHED_ONLY:
            return False, False
    return False, False


def judge_git_args(args):
    """args = tokens after `git`. Returns a deny reason or None."""
    i = 0
    while i < len(args) and args[i].startswith("-"):
        opt = args[i]
        name, _, attached = opt.partition("=")
        if name == "--config-env":
            target = attached or (args[i + 1] if i + 1 < len(args) else "")
            if "hookspath" in target.lower():
                return "`git --config-env core.hooksPath=...` disables the repository's git hooks"
        if opt in GLOBAL_VALUE and i + 1 < len(args):
            val = args[i + 1]
            if opt == "-c" and "hookspath" in val.lower():
                return "`git -c core.hooksPath=...` disables the repository's git hooks"
            if opt == "-c" and val.lower().startswith("alias.") and "=" in val and \
                    alias_bypasses(val.split("=", 1)[1]):
                return "a `git -c alias...` that expands to a hook bypass"
            i += 2
            continue
        i += 1
    if i >= len(args):
        return None
    sub, rest = args[i], args[i + 1:]
    if sub == "config":
        positional = [t for t in rest if not t.startswith("-")]
        reading = any(t in CONFIG_READS for t in rest) or len(positional) <= 1
        if not reading and any("hookspath" in t.lower() for t in positional):
            return "`git config core.hooksPath` redirects the repository's git hooks"
        if not reading and positional[0].lower().startswith("alias.") and \
                alias_bypasses(" ".join(positional[1:])):
            return "`git config alias...` that expands to a hook bypass"
        return None
    if sub not in HOOKED:
        return None
    j = 0
    while j < len(rest):
        t = rest[j]
        if is_no_verify(t):
            return f"`git {sub} {t}` skips the repository's git hooks"
        if sub == "commit" and t.startswith("-") and not t.startswith("--") and len(t) > 1:
            has_n, skip_next = commit_cluster_has_n(t)
            if has_n:
                return "`git commit -n` is --no-verify: it skips the pre-commit hooks"
            if skip_next:
                j += 1
        elif sub == "commit" and t in COMMIT_LONG_VALUE:
            j += 1
        j += 1
    return None


def command_words(seg):
    """Strip leading env assignments and wrappers; return (env assignments, command words)."""
    env, k = [], 0
    while k < len(seg):
        tok = seg[k]
        if ENV_ASSIGN.match(tok):
            env.append(tok)
        elif tok in WRAPPERS_WITH_ARG:
            k += 1
            while k < len(seg) and seg[k].startswith("-"):
                k += 1
        elif tok == "xargs":
            while k + 1 < len(seg) and seg[k + 1].startswith("-"):
                k += 1
        elif tok == "--" and k > 0 and seg[k - 1] in WRAPPERS | WRAPPERS_WITH_ARG | {"xargs"}:
            pass  # `command -- git ...`: end of the wrapper's options (Codex review 2026-10-14)
        elif tok not in WRAPPERS:
            break
        k += 1
    return env, seg[k:]


def nested_command(words, depth):
    """The command string inside `bash|sh -c '...'` / `-lc` or `eval ...`, else None."""
    if depth >= 3 or not words:
        return None
    head = basename(words[0])
    if head in ("bash", "sh", "zsh", "bash.exe", "sh.exe"):
        for k, w in enumerate(words[1:], 1):
            if re.fullmatch(r"-[a-zA-Z]*c[a-zA-Z]*", w) and k + 1 < len(words):
                return words[k + 1]
    if head == "eval":
        return " ".join(words[1:])
    return None


def basename(word):
    return os.path.basename(word.replace(BACKSLASH, "/")).lower()


def git_name(word):
    return basename(word) in ("git", "git.exe")


def judge(seg, exported, depth=0):
    env, words = command_words(seg)
    if not words:
        return None
    head = basename(words[0])
    if head == "export":
        exported.extend(w for w in words[1:] if ENV_ASSIGN.match(w))
        return None
    inner = nested_command(words, depth)
    if inner is not None:
        return judge_command(inner, depth + 1)
    if not git_name(words[0]):
        return None
    if any("hookspath" in e.lower() for e in env + exported):
        return "a GIT_CONFIG_* environment override of core.hooksPath disables the repository's git hooks"
    return judge_git_args(words[1:])


def judge_command(cmd, depth=0):
    exported = []
    for seg in safe_segments(cmd):
        reason = judge(seg, exported, depth)
        if reason:
            return reason
    return None


def classify(cmd, depth=0, cur=""):
    out = {"commit": False, "dirs": []}
    for seg in safe_segments(cmd):
        _env, words = command_words(seg)
        if not words:
            continue
        inner = nested_command(words, depth)
        if inner is not None:  # `bash -lc 'git commit ...'` commits too (Codex review 2026-10-14)
            sub = classify(inner, depth + 1, cur)
            out["commit"] = out["commit"] or sub["commit"]
            out["dirs"] += sub["dirs"]
            continue
        if words[0] in ("cd", "pushd") and len(words) > 1:
            cur = words[1] if os.path.isabs(words[1]) or not cur else os.path.join(cur, words[1])
            continue
        if not git_name(words[0]):
            continue
        args, i, cdir = words[1:], 0, cur
        while i < len(args) and args[i].startswith("-"):
            if args[i] in GLOBAL_VALUE and i + 1 < len(args):
                if args[i] == "-C":
                    cdir = args[i + 1] if os.path.isabs(args[i + 1]) or not cdir else os.path.join(cdir, args[i + 1])
                i += 2
                continue
            i += 1
        if i < len(args) and args[i] == "commit":
            out["commit"] = True
            out["dirs"].append(cdir)
    return out


def main():
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
        cmd = (payload.get("tool_input") or {}).get("command") or ""
    except (ValueError, AttributeError):
        return
    if "--classify" in sys.argv[1:]:
        print(json.dumps(classify(cmd)))
        return
    reason = judge_command(cmd)
    if reason:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason + ". Fix what the hook reports instead; if a bypass is "
                                        "really needed, the human runs that command themselves.",
        }}))


if __name__ == "__main__":
    main()
