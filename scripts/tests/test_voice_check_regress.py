#!/usr/bin/env python3
"""Regression guard — skills/human-voice/scripts/voice-check.py.

The detector is report-only, so a defect here costs credibility rather than correctness: a
rule that fires on ordinary technical Russian teaches the reader to ignore the report, and a
stripper that lets code through inflates a baseline nobody can then trust. Both directions are
pinned. Most cases came from a cross-family review (Codex, 2026-08-27).

  A. STRIPPER      tilde fences, indented code, double-backtick spans, table rows, a BOM'd
                   frontmatter block and a `...`-terminated one must not reach the rules.
  B. NOT A DEFECT  a measurement stated next to a degree word or a quality word is the thing
                   the rule asks for, so it must not be flagged.
  C. STILL FIRES   the padding the rules exist for must still be caught, otherwise the fixes
                   above have quietly disabled the detector.
  D. NEGATIVE      the user's own Russian scores zero on the artefact surface.

Run standalone or under pytest:
  python test_voice_check_regress.py
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

SKILL_DIR = Path.home() / ".claude" / "skills" / "human-voice"
_spec = importlib.util.spec_from_file_location("_voice_check", SKILL_DIR / "scripts" / "voice-check.py")
vc = importlib.util.module_from_spec(_spec)
sys.modules["_voice_check"] = vc
_spec.loader.exec_module(vc)


def hits(text: str, surface: str = "artefact") -> dict[str, int]:
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "doc.md"
        f.write_text(text, encoding="utf-8")
        res = vc.scan([f], surface=surface)
    return {k: len(v) for k, v in res["hits"].items() if v}


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok and detail:
        print(f"         {detail}")
    return ok


SLOP = "Важно отметить, что сервис работает корректно.\n"


def main() -> int:
    r = []

    print("A. stripper keeps non-prose out")
    for label, text in [
        ("tilde fence", f"~~~text\n{SLOP}~~~\n"),
        ("backtick fence", f"```text\n{SLOP}```\n"),
        ("indented code block", "    " + SLOP),
        ("double-backtick span", f"``{SLOP.strip()}``\n"),
        ("table row", "| Режим | Сервис является доступным |\n"),
        ("BOM'd frontmatter", "﻿---\ndescription: " + SLOP + "---\n\nОбычный текст тут.\n"),
    ]:
        got = hits(text)
        r.append(check(f"{label} produces no hits", not got, f"got {got}"))

    print("\n  ...and a `...`-terminated frontmatter does not swallow the body")
    got = hits("---\nname: x\n...\n\n" + SLOP)
    r.append(check("body after `...` is still scanned", bool(got), f"got {got}"))

    print("\nB. a stated measurement is not the defect the rule looks for")
    for label, text in [
        ("intensifier beside real numbers",
         "Тесты существенно сократили время ответа с 500 до 120 мс.\n"),
        ("quality word beside a real number",
         "Оптимальный размер буфера равен 64 КБ.\n"),
    ]:
        got = hits(text)
        r.append(check(f"{label} -> no hit", not got, f"got {got}"))
    got = hits("Однозначно определяем маршрут по заголовку Content-Type.\n")
    r.append(check("`однозначно` as 'deterministically' -> no hit", not got, f"got {got}"))

    print("\nC. the padding it exists for still fires")
    for label, text, rule in [
        ("filler-open", "Важно отметить, что подпись проверяется на сервере.\n", "filler-open"),
        ("kancelarit", "Проверка подписи осуществляется на сервере.\n", "kancelarit"),
        ("intensifier with no number", "Отчёт существенно улучшил читаемость выводов.\n", "intensifier"),
        ("vague-quality with no number", "Мы сделали удобный интерфейс для оператора.\n", "vague-quality"),
        ("unproven", "Безусловно, миграция пройдёт без потерь данных.\n", "unproven"),
    ]:
        got = hits(text)
        r.append(check(f"{label} still caught", rule in got, f"got {got}"))
    got = hits("Версия 1.2 — это стабильный релиз проекта.\n", surface="deliverable")
    r.append(check("dash fires on the deliverable surface", "dash" in got, f"got {got}"))
    got = hits("Версия 1.2 — это стабильный релиз проекта.\n", surface="artefact")
    r.append(check("dash stays silent on the artefact surface", "dash" not in got, f"got {got}"))

    print("\nD. negative fixture — the user's own Russian")
    brief = Path.home() / ".claude" / "NEXT-SESSION-humanizer.md"
    if brief.exists():
        res = vc.scan([brief], surface="artefact")
        total = sum(len(v) for v in res["hits"].values())
        r.append(check(f"{brief.name} scores 0 on the artefact surface", total == 0,
                       f"got {total}: { {k: len(v) for k, v in res['hits'].items() if v} }"))
    else:
        print(f"  [SKIP] {brief.name} not present")

    failed = r.count(False)
    print(f"\n{len(r) - failed}/{len(r)} checks passed")
    return 1 if failed else 0


def test_voice_check_regression():
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
