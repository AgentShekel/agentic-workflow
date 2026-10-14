#!/usr/bin/env python3
"""PostToolUse(Edit|Write) lint hook: fix only the lines the edit touched.

New files (Write with tool_response.type == "create") get every safe autofix, all
rows counting as the edit's. Existing files get only safe autofixes whose every edit
lands on a line the tool call added or changed (tool_response.structuredPatch);
every other line stays byte-identical. Both re-read the file before writing and
drop the pass if it moved (another edit or session landed while the linter ran).
Findings on the touched lines go back to the model as
additionalContext, with a count of the pre-existing findings elsewhere.

Line identity is tracked through the applied edits, never by matching content:
each untouched line is followed by offset, and a pass is kept only if every
untouched line survives as a whole line with the same bytes.

Linters: ruff (.py/.pyi), ESLint (.ts/.tsx/.js/.jsx/.mjs/.cjs, nearest
node_modules/.bin/eslint), shellcheck (.sh/.bash, report only).
"""

import bisect
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

MAX_PASSES = 3  # fixes can unlock further fixes; ruff --fix loops the same way
MAX_REPORTED = 10
# Edits land in steps: an import or a noqa written now is often used by the next edit.
# Removing it in between broke runs twice (NameError), so these are reported, never fixed.
RUFF_NO_FIX = {"F401", "RUF100"}
DEADLINE = time.monotonic() + 24  # settings.json allows 30s; keep room to report
LINE_RE = re.compile(r"[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+$")


def touched_lines(response):
    """1-based line numbers of the post-edit file that the tool call added or changed."""
    touched = set()
    for hunk in response.get("structuredPatch") or []:
        n = hunk.get("newStart", 1)
        for line in hunk.get("lines", []):
            tag = line[:1]
            if tag == "+":
                touched.add(n)
                n += 1
            elif tag == " ":
                n += 1
            # "-" lines are gone from the new file; "\" is the no-newline marker
    return touched


# --- text and edits -------------------------------------------------------------

def run(cmd, cwd=None):
    """stdout of cmd, or None if it could not run inside the shared deadline."""
    timeout = DEADLINE - time.monotonic()
    if timeout < 1:
        return None
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout.decode("utf-8", "replace")


def read_text(path):
    with open(path, "rb") as f:
        raw = f.read()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def write_text(path, text):
    """Atomic replace; encoding happens before the file is touched."""
    data = text.encode("utf-8")
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), prefix=".lint-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def line_starts(text):
    return [m.start() for m in LINE_RE.finditer(text)] or [0]


def offset_of(text, starts, row, column):
    """Ruff location (1-based row, 1-based code-point column) to a str index."""
    return len(text) if row > len(starts) else starts[row - 1] + column - 1


def row_of(starts, i):
    return max(bisect.bisect_right(starts, i), 1)


def span_rows(start_row, end_row, end_col):
    """Rows an edit rewrites; an end at column 1 of a later row stops on the row before."""
    if end_row > start_row and end_col == 1:
        end_row -= 1
    return set(range(start_row, end_row + 1))


def apply_edits(text, edits):
    for s, e, c in sorted(edits, reverse=True):
        text = text[:s] + c + text[e:]
    return text


def apply_tracked(text, touched, edits):
    """Apply edits; return (new_text, new_touched), or None if an untouched line would change.

    An untouched line must come out with the same bytes, starting at a line start and
    ending at a line start or EOF: a fix that eats the line break before it, or glues a
    CR onto its LF, merges it into a touched line and is refused.
    """
    starts = line_starts(text)
    ends = starts[1:] + [len(text)]
    new = apply_edits(text, edits)
    new_starts = line_starts(new)
    boundaries = set(new_starts) | {len(new)}
    kept = set()
    for row, (s, e) in enumerate(zip(starts, ends), 1):
        if row in touched or e == s:
            continue
        ns = s + sum(len(c) - (ee - es) for es, ee, c in edits if ee <= s)
        if new[ns:ns + e - s] != text[s:e] or ns not in boundaries or ns + e - s not in boundaries:
            return None
        kept.add(row_of(new_starts, ns))
    return new, set(range(1, len(new_starts) + 1)) - kept


def choose(text, touched, groups):
    """Whole fix groups whose rows are all touched, that overlap no earlier pick, and that
    leave every untouched line intact on their own. A group is a list of
    (start, end, content, rows); a fix applies entirely or not at all."""
    picked = []
    for group in sorted((g for g in groups if g), key=lambda g: min(e[0] for e in g)):
        edits = [(s, e, c) for s, e, c, _ in group]
        if not all(0 <= s <= e <= len(text) for s, e, _ in edits):
            continue
        if not set().union(*(rows for *_, rows in group)) <= touched:
            continue
        if any(s == ps or (s < pe and ps < e) for s, e, _ in edits for ps, pe, _ in picked):
            continue
        if apply_tracked(text, touched, edits) is None:
            continue
        picked.extend(edits)
    return picked


def fix_touched(path, touched, check):
    """Fix the touched rows pass by pass.

    Returns (findings, touched) for the final file. findings is None only when a pass
    wrote fixes and the re-check could not run; [] when nothing could be checked at all.
    """
    text = read_text(path)
    if text is None:
        return check("")[1] or [], touched
    wrote = False
    for _ in range(MAX_PASSES):
        groups, findings = check(text)
        edits = choose(text, touched, groups)
        result = apply_tracked(text, touched, edits) if edits else None
        if result is None or result[0] == text:
            return (findings if findings is not None or wrote else []), touched
        # The linter ran for a while; if the file moved meanwhile (another edit, another
        # session on the same checkout), writing our snapshot back would revert that edit.
        # Drop the pass instead (Codex review 2026-10-09).
        if read_text(path) != text:
            return [], touched
        text, touched = result
        write_text(path, text)
        wrote = True
    return check(text)[1], touched


def fix_created(path, check):
    """A file the tool call created: every row is the edit's, so every safe fix may land.

    Goes through fix_touched, not the linter's own --fix: that path re-reads before it
    writes, so an edit landing while the linter runs is not reverted (Codex review
    2026-10-09). Returns findings for the whole file, or None as fix_touched does.
    """
    text = read_text(path)
    rows = set(range(1, len(line_starts(text)) + 1)) if text else set()
    return fix_touched(path, rows, check)[0]


# --- ruff ---------------------------------------------------------------------

def ruff_check(ruff, path, text):
    out = run([ruff, "check", "--output-format", "json", "--no-cache", path])
    try:
        diags = json.loads(out) if out else None
    except json.JSONDecodeError:
        diags = None
    if diags is None:
        return [], None
    starts = line_starts(text)
    groups = []
    for d in diags:
        fix = d.get("fix") or {}
        if fix.get("applicability") != "safe" or d.get("code") in RUFF_NO_FIX:
            continue
        groups.append([(offset_of(text, starts, **e["location"]),
                        offset_of(text, starts, **e["end_location"]),
                        e["content"],
                        span_rows(e["location"]["row"], e["end_location"]["row"],
                                  e["end_location"]["column"]))
                       for e in fix.get("edits") or []])
    findings = [(d["location"]["row"], d["location"]["column"], d["code"] or "syntax", d["message"])
                for d in diags]
    return groups, findings


def python_linter(path):
    ruff = shutil.which("ruff")
    if not ruff:
        return None
    return ("Ruff",
            lambda text: ruff_check(ruff, path, text),
            lambda: run([ruff, "check", "--fix", "--unfixable", ",".join(sorted(RUFF_NO_FIX)), "--quiet", path]))


# --- eslint -------------------------------------------------------------------

def find_eslint(path):
    d = os.path.dirname(os.path.abspath(path))
    while True:
        exe = shutil.which("eslint", path=os.path.join(d, "node_modules", ".bin"))
        if exe:
            return exe, d
        parent = os.path.dirname(d)
        if parent == d:
            return None, None
        d = parent


def utf16_to_index(text):
    """Map ESLint's UTF-16 code-unit offsets to Python str indexes."""
    table = []
    for i, ch in enumerate(text):
        table.append(i)
        if ord(ch) > 0xFFFF:
            table.append(i)
    table.append(len(text))
    return table


def eslint_check(exe, cwd, path, text):
    out = run([exe, "--format", "json", path], cwd=cwd)
    try:
        messages = (json.loads(out) or [{}])[0].get("messages", []) if out else None
    except (json.JSONDecodeError, IndexError, AttributeError):
        messages = None
    if messages is None:
        return [], None
    bom = 1 if text.startswith(chr(0xFEFF)) else 0  # ESLint's ranges skip the BOM
    body = text[bom:]
    idx = utf16_to_index(body)
    starts = line_starts(body)
    groups = []
    for m in messages:
        if "unused" in (m.get("ruleId") or ""):
            continue  # same stepwise-edit reason as RUFF_NO_FIX
        r = (m.get("fix") or {}).get("range")
        # The BOM-removal fix uses range [-1, 0]; anything outside the body is not ours.
        if not (isinstance(r, list) and len(r) == 2 and 0 <= r[0] <= r[1] < len(idx)):
            continue
        s, e = idx[r[0]], idx[r[1]]
        end_row = row_of(starts, e)
        rows = span_rows(row_of(starts, s), end_row, e - starts[end_row - 1] + 1)
        groups.append([(s + bom, e + bom, m["fix"].get("text", ""), rows)])
    findings = [(m.get("line", 0), m.get("column", 0), m.get("ruleId") or "parse", m.get("message", ""))
                for m in messages]
    return groups, findings


def js_linter(path):
    exe, cwd = find_eslint(path)
    if not exe:
        return None
    return ("ESLint",
            lambda text: eslint_check(exe, cwd, path, text),
            lambda: run([exe, "--fix", path], cwd=cwd))


# --- shellcheck ---------------------------------------------------------------

def shell_check(sc, path):
    out = run([sc, "-f", "gcc", path])
    if out is None:
        return [], None
    findings = []
    for line in out.splitlines():
        m = re.match(r".*?:(\d+):(\d+): (\w+): (.*)$", line)
        if m and m.group(3) in ("error", "warning"):
            findings.append((int(m.group(1)), int(m.group(2)), m.group(3), m.group(4)))
    return [], findings


def shell_linter(path):
    sc = shutil.which("shellcheck")
    if not sc:
        return None
    return "ShellCheck", lambda text: shell_check(sc, path), None


LINTERS = [
    ((".py", ".pyi"), python_linter),
    ((".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"), js_linter),
    ((".sh", ".bash"), shell_linter),
]


# --- entry --------------------------------------------------------------------

def emit(context):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": context,
    }}))


def main():
    try:
        # Bytes, decoded as UTF-8: without PYTHONUTF8 or a UTF-8 system code page, Windows Python
        # decodes piped stdin with the ANSI code page and Cyrillic file content would fail here.
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return
    if payload.get("tool_name") not in ("Edit", "Write"):
        return
    path = (payload.get("tool_input") or {}).get("file_path", "")
    if not path or not os.path.isfile(path):
        return
    factory = next((fn for exts, fn in LINTERS if path.lower().endswith(exts)), None)
    linter = factory(path) if factory else None
    if not linter:
        return
    name, check, _ = linter  # third element (the linter's own --fix) is no longer used
    base = os.path.basename(path)

    response = payload.get("tool_response") or {}
    if response.get("type") == "create":
        findings, touched = fix_created(path, check), None
    else:
        findings, touched = fix_touched(path, touched_lines(response), check)
    if findings is None:
        emit(f"{name}: autofixed {base}, but the re-check did not finish in time; run {name.lower()} on it.")
        return

    mine = sorted(f for f in findings if touched is None or f[0] in touched)
    if not mine:
        return
    lines = [f"{name}: {len(mine)} finding(s) on the lines this edit wrote:"]
    lines += [f"  {base}:{r}:{c}: {code} {msg}" for r, c, code, msg in mine[:MAX_REPORTED]]
    if len(mine) > MAX_REPORTED:
        lines.append(f"  ... {len(mine) - MAX_REPORTED} more")
    others = len(findings) - len(mine)
    if others:
        lines.append(f"  ({others} pre-existing finding(s) elsewhere in the file left untouched)")
    emit("\n".join(lines))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 — a lint hook must never break the edit it follows
        emit(f"lint_on_edit hook crashed: {type(exc).__name__}: {exc}. Re-read the file before the next edit.")
