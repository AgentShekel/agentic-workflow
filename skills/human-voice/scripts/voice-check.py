#!/usr/bin/env python3
"""Detector for the human-voice rules. Reports, never rewrites.

The point is measurement, not correction. A rule that fires on nothing is dead weight; a rule
that fires on everything is a rule about the language rather than about the text. Run this over
real past artefacts before trusting any rule, and record the rate.

Scope: RUSSIAN prose lines only. A line qualifies when it holds >= MIN_CYR_WORDS cyrillic words.
Fenced code, inline code spans, link targets, YAML frontmatter and HTML comments are stripped
first, so a `--per_page` flag or an English preflight note never counts as prose.

Usage:
  voice-check.py PATH [PATH ...]          human report
  voice-check.py PATH --json              machine-readable
  voice-check.py PATH --rule dash         one rule, with every hit quoted
  voice-check.py PATH --samples 5         quote N examples per rule
"""
from __future__ import annotations

import sys as _sys

try:
    _sys.stdout.reconfigure(encoding="utf-8")
    _sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

MIN_CYR_WORDS = 3
CYR_WORD = re.compile(r"[А-Яа-яЁё]{3,}")

# Each rule names a CAUSE, not a symptom. `why` is what the agent should do instead; it is
# printed in the report so a hit is actionable without opening the skill.
#
# `surface` decides where a rule is allowed to fire:
#   deliverable  RU text a human reads as prose they did not write: chat replies, README,
#                landing / pitch copy, plans and reports written FOR the reader.
#   both         substance rules that hold regardless of the medium.
# The split is load-bearing. On engagement artefacts the dash rule fires constantly, and
# almost every hit is a STRUCTURAL dash after a bold lead-in, not prose flow. A rule about
# prose applied to structured documents produces a number that means nothing.
RULES: dict[str, dict] = {
    "dash": {
        "surface": "deliverable",
        "why": "em/en dash in Russian prose. Use a colon, a period, a comma or parentheses.",
        "re": re.compile(r"[—–]"),
    },
    "filler-open": {
        "surface": "both",
        "why": "opening phrase that carries no information. Delete it and start with the fact.",
        "re": re.compile(
            r"\b(важно\s+(?:отметить|понимать|учитывать)|стоит\s+отметить|следует\s+(?:отметить|учитывать|понимать)"
            r"|необходимо\s+(?:отметить|понимать)|как\s+известно|в\s+целом\s+можно\s+сказать"
            r"|хочется\s+отметить|нельзя\s+не\s+отметить)\b", re.IGNORECASE),
    },
    "filler-close": {
        "surface": "both",
        "why": "moralising wrap-up. The text already said it; end on the last fact.",
        "re": re.compile(
            r"\b(в\s+конечном\s+(?:счёте|счете|итоге)|таким\s+образом,?\s+можно\s+сделать\s+вывод"
            r"|подводя\s+ито[гж]|главное\s+(?:—|-|:)?\s*помнить|в\s+заключение\s+(?:стоит|хочется|можно))\b", re.IGNORECASE),
    },
    "kancelarit": {
        "surface": "both",
        "why": "bureaucratic connective. Name the actor and the verb instead.",
        "re": re.compile(
            # `данн(ый|ая|ое|ого|…)` only in its demonstrative forms. «данные» is the ordinary
            # technical noun for data and produced most of the false hits in calibration.
            r"\b(являет(?:ся|ются)|осуществляет(?:ся|ются)|производится\s+\w+ние"
            r"|данн(?:ый|ая|ое|ого|ому|ым|ом)\b|в\s+рамках\s+данн|на\s+сегодняшний\s+день"
            r"|в\s+связи\s+с\s+тем,?\s+что|представляет\s+собой)\b", re.IGNORECASE),
    },
    "vague-quality": {
        "surface": "both",
        "why": "quality claim with no observable criterion. State what is measured and how.",
        "re": re.compile(
            r"\b(работает\s+(?:корректно|правильно|как\s+ожидается)|удобн(?:ый|ая|ое|ые)\s+интерфейс"
            r"|улучшить\s+(?:ux|юзабилити|удобство)|повысить\s+эффективность|оптимальн(?:ый|ая|ое)\s+\w+"
            r"|качественн(?:ый|ая|ое)\s+\w+|быстро\s+отвечает|высок(?:ая|ое)\s+производительность)\b", re.IGNORECASE),
    },
    "stamp": {
        "surface": "both",
        "why": "stock phrase that reads as machine-written. Say the concrete thing it stands for.",
        "re": re.compile(
            r"\b(не\s+чёрн(?:ый|ым)\s+ящик|бесшовн|из\s+коробки|на\s+лету|в\s+современном\s+мире"
            r"|ключев(?:ая|ое)\s+особенность|заземл(?:яем|ены|яет)|в\s+связке\s+с\s+человеком"
            r"|помогает,?\s+а\s+не\s+заменяет|под\s+капотом|мощн(?:ый|ая|ое)\s+инструмент)\b", re.IGNORECASE),
    },
    "intensifier": {
        "surface": "both",
        "why": "degree adverb standing in for a number. Give the number or drop the adverb.",
        "re": re.compile(
            r"\b(значительно|существенно|кардинально|весьма|крайне|максимально|полностью)\s+"
            r"(?![^\s]*\d)", re.IGNORECASE),
    },
    "unproven": {
        "surface": "both",
        "why": "asserts certainty the text has not earned. Say what was checked, or say it is unverified.",
        # `однозначно` was dropped: in technical Russian it usually reads as
        # "deterministically" ("однозначно определяем маршрут по заголовку"), not "certainly".
        # The remaining four carry no such second reading.
        "re": re.compile(r"\b(очевидно,?\s+что|безусловно|несомненно|разумеется,?\s+что)\b",
                         re.IGNORECASE),
    },
}

# Backtick AND tilde fences: `~~~` is valid Markdown and its contents are code just the same.
# The character is captured so a fence can only be closed by its OWN kind — otherwise a `~~~`
# line inside a backtick block ends it early and the code that follows is scanned as prose.
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
FRONTMATTER = re.compile(r"^---\s*$")
# Double-backtick spans first, then single. Matching single first eats the empty `` pair and
# leaves the code text exposed to the rules.
INLINE_CODE = re.compile(r"``.+?``|`[^`]*`", re.DOTALL)
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
LINK_TARGET = re.compile(r"\]\([^)]*\)")
# Any table row, not only the separator. A cell is structured content, and phrasing rules about
# prose have no purchase on it.
TABLE_ROW = re.compile(r"^\s*\|")
TABLE_SEP = re.compile(r"^\s*\|?[\s:|-]+\|[\s:|-]*$")
# Four spaces or a tab is an indented code block in Markdown.
INDENTED_CODE = re.compile(r"^(?: {4}|\t)")
# Quoted material is someone else's words, including this rule set quoting its own banned
# phrases. Without this, any document that DISCUSSES the rules trips them: the brief that
# specified this skill scored two hits, both on the table row listing what to forbid.
QUOTED = re.compile(r"«[^»]*»|“[^”]*”|\"[^\"]*\"")


def prose_lines(text: str):
    """Yield (lineno, cleaned_line) for Russian prose only."""
    # Strip a UTF-8 BOM: with it in place the first line is not `---`, frontmatter goes
    # undetected, and YAML descriptions get scanned as if they were prose.
    text = HTML_COMMENT.sub(" ", text.lstrip("﻿"))
    fence_marker: str | None = None
    in_fm = False
    seen_content = False
    for i, raw in enumerate(text.splitlines(), 1):
        m = FENCE.match(raw)
        if m:
            marker = m.group(1)
            if fence_marker is None:
                fence_marker = marker[0]
                continue
            # Close only on the same fence character, and only on a run at least as long.
            if marker[0] == fence_marker:
                fence_marker = None
            continue
        if fence_marker is not None:
            continue
        # Frontmatter may sit after a blank line or two; anchoring on line 1 alone let those
        # files through and scanned their YAML as prose.
        if not seen_content and FRONTMATTER.match(raw):
            in_fm = True
            seen_content = True
            continue
        if raw.strip():
            seen_content = True
        if in_fm:
            # `...` closes a YAML document too. Without it a stray terminator would leave the
            # stripper in frontmatter mode and silently swallow the entire rest of the file.
            if FRONTMATTER.match(raw) or raw.strip() == "...":
                in_fm = False
            continue
        if TABLE_SEP.match(raw) or TABLE_ROW.match(raw) or INDENTED_CODE.match(raw):
            continue
        line = QUOTED.sub(" ", LINK_TARGET.sub("]", INLINE_CODE.sub(" ", raw)))
        if len(CYR_WORD.findall(line)) >= MIN_CYR_WORDS:
            yield i, line


# Rules about a word standing IN PLACE OF a measurement. When the line carries a measurement,
# the word is doing something else: "существенно сократили время ответа с 500 до 120 мс" and
# "оптимальный размер буфера равен 64 КБ" both state the number the rule asks for. The original
# lookahead only inspected the next token and missed both.
NUMERIC_EXEMPT = {"intensifier", "vague-quality"}
HAS_DIGIT = re.compile(r"\d")


# Rules about a word standing IN PLACE OF a measurement. When the measurement is right there,
# the word is doing something else: "существенно сократили время ответа с 500 до 120 мс" and
# "оптимальный размер буфера равен 64 КБ" both state the number the rule asks for.
#
# The exemption is scoped to what FOLLOWS the match, within NUMERIC_WINDOW characters. Checking
# the whole line was too generous in the other direction: "В версии 2 есть удобный интерфейс"
# has a digit that has nothing to do with the quality claim, and the hit was being dropped.
NUMERIC_EXEMPT = {"intensifier", "vague-quality"}
NUMERIC_WINDOW = 40
HAS_DIGIT = re.compile(r"\d")


def active_rules(surface: str) -> dict[str, dict]:
    return {rid: r for rid, r in RULES.items()
            if r["surface"] == "both" or r["surface"] == surface}


def scan(paths: list[Path], surface: str = "deliverable") -> dict:
    rules = active_rules(surface)
    files = []
    for p in paths:
        if p.is_dir():
            files.extend(sorted(p.rglob("*.md")))
        elif p.is_file():
            files.append(p)
    hits: dict[str, list] = defaultdict(list)
    scanned = 0
    ru_files = 0
    ru_lines = 0
    per_file_flagged = Counter()
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        scanned += 1
        lines = list(prose_lines(text))
        if not lines:
            continue
        ru_files += 1
        ru_lines += len(lines)
        for lineno, line in lines:
            for rid, rule in rules.items():
                for m in rule["re"].finditer(line):
                    if rid in NUMERIC_EXEMPT and HAS_DIGIT.search(
                            line[m.end():m.end() + NUMERIC_WINDOW]):
                        continue
                    hits[rid].append({"file": str(f), "line": lineno,
                                      "match": m.group(0).strip(),
                                      "context": line.strip()[:160]})
                    per_file_flagged[str(f)] += 1
    return {"surface": surface, "rules": list(rules), "scanned": scanned,
            "ru_files": ru_files, "ru_lines": ru_lines,
            "hits": dict(hits), "files_flagged": len(per_file_flagged)}


def main() -> int:
    ap = argparse.ArgumentParser(description="human-voice rule detector (report only)")
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--rule", help="show every hit for one rule id")
    ap.add_argument("--samples", type=int, default=2, help="examples quoted per rule")
    ap.add_argument("--surface", choices=["deliverable", "artefact"], default="deliverable",
                    help="deliverable = RU prose a human reads (chat, README, landing, plans "
                         "written for him); artefact = structured engagement/tech docs, where "
                         "the prose-shape rules do not apply")
    args = ap.parse_args()

    res = scan([Path(p) for p in args.paths], surface=args.surface)

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    if args.rule:
        for h in res["hits"].get(args.rule, []):
            print(f"{h['file']}:{h['line']}  «{h['match']}»")
            print(f"    {h['context']}")
        return 0

    total = sum(len(v) for v in res["hits"].values())
    print(f"surface={res['surface']}  rules={len(res['rules'])}")
    print(f"scanned {res['scanned']} file(s); {res['ru_files']} hold Russian prose "
          f"({res['ru_lines']} prose lines)")
    print(f"{total} hit(s) across {res['files_flagged']} file(s)\n")
    if not res["ru_lines"]:
        return 0
    for rid in res["rules"]:
        hs = res["hits"].get(rid, [])
        rate = 1000.0 * len(hs) / res["ru_lines"]
        print(f"  {rid:<14} {len(hs):>4} hit(s)   {rate:>6.1f} per 1000 prose lines")
        if hs:
            print(f"      {RULES[rid]['why']}")
            for h in hs[:args.samples]:
                print(f"      · {Path(h['file']).name}:{h['line']} «{h['match']}»")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
