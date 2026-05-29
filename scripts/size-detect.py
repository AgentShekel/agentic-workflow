#!/usr/bin/env python3
"""Engagement size tier detector + auto-promote.

Two modes:

  --mode intake   — heuristic guess based on criteria.md text alone.
                    Used by agency-intake to suggest S/M/L while writing frontmatter.
                    Output: {suggested: S|M|L, current: S|M|L, reason: "..."}.
                    Exit 0 always (advisory).

  --mode runtime  — measures real engagement state (executor-reports count,
                    tasks count, ui artefacts, deploy-log, diff-summary in
                    handoff if any) against tier thresholds. If real size
                    exceeds frontmatter size, signals promote.
                    Output: {current: S, observed: M, reason: "...", promote: true|false}.
                    Exit 0 if no promote needed, 1 if promote suggested,
                    2 on error.

  --auto-promote  — runtime mode only. Instead of just signalling, actually
                    rewrite criteria.md frontmatter (S→M or M→L only, never
                    demote) AND append an entry to scope-sync.md documenting
                    the auto-promote decision. Lead acks via heartbeat.

Exit codes:
  0 — match (or intake advisory)
  1 — promote suggested (runtime) / size mismatch
  2 — invocation error

Usage:
  python ~/.claude/scripts/size-detect.py engagement/ --mode intake --json
  python ~/.claude/scripts/size-detect.py engagement/ --mode runtime --json
  python ~/.claude/scripts/size-detect.py engagement/ --mode runtime --auto-promote
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
import sys
from datetime import datetime, timezone
from pathlib import Path

SIZE_ORDER = {"S": 0, "M": 1, "L": 2}
SIZE_NAMES = ["S", "M", "L"]


# Heuristic signals that nudge intake guess upward
INTAKE_L_SIGNALS = [
    r"\brebrand\b", r"\bredesign\b", r"\brefactor(?:ing)?\b",
    r"\bmulti-?(wave|phase|stage)\b", r"\bnew\s+(project|product|service)\b",
    r"\bmigration\b", r"\barchitecture\s+change\b", r"\binfra(?:structure)?\s+overhaul\b",
    r"\bfull\s+(audit|rebuild|redesign)\b",
    r"\bцелый\s+(сайт|проект|редизайн)\b", r"\bперестройка\b", r"\bмиграция\b",
    r"\bновый\s+(проект|продукт|сервис)\b",
]

INTAKE_M_SIGNALS = [
    r"\blanding(\s+page)?\b", r"\bdashboard\b", r"\bcampaign\b",
    r"\bfeature\b", r"\bcomponent\s+library\b", r"\bdesign\s+system\b",
    r"\baudit\b", r"\banalysis\b", r"\bseo(\s+audit)?\b",
    r"\bлендинг\b", r"\bдашборд\b", r"\bкампания\b",
    r"\bаудит\b", r"\bдизайн[- ]?систем\b",
]

INTAKE_S_SIGNALS = [
    r"\bfix(\s+a)?\s+\w+\b", r"\btweak\b", r"\bupdate\s+(text|copy|colour|color)\b",
    r"\bsmall\s+(change|update|fix)\b", r"\bquick\b",
    r"\bправк[аи]\b", r"\bпочин(и|ить)\b", r"\bобнов(и|ить)\s+текст\b",
    r"\bмелк(ая|ие)\s+(правк|задач)\b",
]

# Structural narrowness signals — explicit scope-limiting language that marks
# an S task regardless of how many done-when bullets were written.
# Structural facts (one file / one endpoint / no migration / mirrors
# existing code) must
# outweigh bullet count, which had over-inflated legitimate S tasks to M.
STRUCTURAL_S_SIGNALS = [
    r"\b(?:one|single)\s+file\b", r"\b(?:one|single)\s+endpoint\b",
    r"\b(?:one|single)\s+function\b", r"\b(?:one|single)\s+method\b",
    r"\b(?:one|single)\s+component\b", r"\bone[- ]?liner?\b",
    r"\bno\s+migration", r"\bno\s+schema\s+change", r"\bno\s+db\s+change",
    r"\bno\s+new\s+(?:dependenc|deps?|packages?|librar)",
    r"\bmirror(?:s|ing)?\s+(?:the\s+)?(?:existing|house|current)\b",
    r"\b(?:existing|house)\s+pattern\b", r"\bsame\s+pattern\s+as\b",
    # RU
    r"\bодин\s+файл\b", r"\bодного\s+файла\b", r"\bодна\s+функци",
    r"\bодин\s+(?:эндпоинт|метод|компонент)\b", r"\bбез\s+миграц",
    r"\bбез\s+(?:новых\s+)?зависимост", r"\bбез\s+изменени[йя]\s+схем",
    r"\bзеркал", r"\bпо\s+образцу\b", r"\bтот\s+же\s+паттерн\b",
]


def read_criteria_meta(eng: Path) -> dict:
    """Read frontmatter fields from criteria.md."""
    crit = eng / "criteria.md"
    if not crit.exists():
        return {}
    text = crit.read_text(encoding="utf-8")
    fm = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not fm:
        return {}
    body = fm.group(1)
    meta = {"_full_text": text, "_frontmatter": body}
    for k in ["size", "ux_heavy", "domain", "engagement"]:
        m = re.search(rf"^{k}\s*:\s*(\S+)", body, re.MULTILINE)
        if m:
            meta[k] = m.group(1).strip().strip('"').strip("'")
    return meta


def count_deliverables(criteria_text: str) -> int:
    """Count bullet items under '## Deliverables expected' and '## Done when'."""
    count = 0
    for header in ["Deliverables expected", "Done when"]:
        block = re.search(
            rf"^##\s+{re.escape(header)}.*?(?=^##\s|\Z)",
            criteria_text, re.MULTILINE | re.DOTALL,
        )
        if block:
            bullets = re.findall(r"^\s*[-*]\s+\S", block.group(0), re.MULTILINE)
            count += len(bullets)
    return count


def strip_out_of_scope(text: str) -> str:
    """Remove '## Explicitly out of scope' block — its keywords are negations,
    not signals. A criterion that says 'NOT a redesign' shouldn't pull intake to L.
    """
    return re.sub(
        r"^##\s+Explicitly\s+out\s+of\s+scope.*?(?=^##\s|\Z)",
        "",
        text, flags=re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )


def intake_heuristic(eng: Path) -> dict:
    """Guess size from criteria.md content alone."""
    meta = read_criteria_meta(eng)
    if not meta:
        return {
            "mode": "intake", "status": "error", "current": None, "suggested": None,
            "reason": "criteria.md missing or has no frontmatter",
        }

    text_full = meta.get("_full_text", "")
    text = strip_out_of_scope(text_full)
    current = (meta.get("size") or "").upper() or None
    ux_heavy = (meta.get("ux_heavy") or "false").lower()
    domain = (meta.get("domain") or "").lower()

    # Score: start at M (default), bump up/down on signals
    score = 1  # M
    reasons: list[str] = []

    deliverable_count = count_deliverables(text)
    if deliverable_count >= 8:
        score += 1
        reasons.append(f"{deliverable_count} deliverables/done-when bullets (≥8 → L pull)")
    elif deliverable_count <= 2:
        score -= 1
        reasons.append(f"{deliverable_count} deliverables/done-when bullets (≤2 → S pull)")

    # ux_heavy=true alone is M-pull; combined with rebrand/redesign → L
    if ux_heavy == "true":
        reasons.append("ux_heavy=true (M floor)")
        if score < 1:
            score = 1

    # Keyword scan
    text_lc = text.lower()
    # Negation guard: phrases like "no migration", "without schema change",
    # "no new dependency" must NOT trip L/M keyword signals (the bare word
    # "migration" inside "no migration" would otherwise read as an L pull).
    # Strip the negated head for the L/M/S keyword scan only; the structural-S
    # scan below still sees the original text and reads "no migration" as S.
    text_kw = re.sub(
        r"\b(?:no|without|not|zero|никак\w*|без|нет)\s+(?:new\s+|новы\w+\s+)?\w+",
        " ",
        text_lc,
    )
    l_hits = [p for p in INTAKE_L_SIGNALS if re.search(p, text_kw, re.IGNORECASE)]
    m_hits = [p for p in INTAKE_M_SIGNALS if re.search(p, text_kw, re.IGNORECASE)]
    s_hits = [p for p in INTAKE_S_SIGNALS if re.search(p, text_kw, re.IGNORECASE)]

    if l_hits:
        score += 1
        reasons.append(f"L-signal keywords: {[h.strip(chr(92)+chr(98)) for h in l_hits[:3]]}")
    if s_hits and not l_hits and not m_hits:
        score -= 1
        reasons.append(f"S-signal keywords: {[h.strip(chr(92)+chr(98)) for h in s_hits[:3]]}")
    if m_hits and not l_hits:
        reasons.append(f"M-signal keywords: {[h.strip(chr(92)+chr(98)) for h in m_hits[:3]]}")

    # Structural narrowness OVERRIDES bullet count. A task that names
    # concrete scope limits
    # (one file / no migration / mirrors existing code) is structurally S
    # even with several done-when bullets. Gated so a legitimate L keyword,
    # ux_heavy floor, or cross-domain floor still holds the size up.
    struct_s_hits = [p for p in STRUCTURAL_S_SIGNALS if re.search(p, text_lc, re.IGNORECASE)]
    if struct_s_hits and not l_hits and ux_heavy != "true":
        score -= 2
        reasons.append(
            "structural-S signals override bullet count: "
            f"{[h.strip(chr(92)+chr(98)) for h in struct_s_hits[:3]]}"
        )

    # cross-domain criteria.md hint = L floor
    if "Cross-domain dependency" in text and "Secondary domain" in text:
        reasons.append("cross-domain dependency declared (L floor)")
        score = max(score, 2)

    score = max(0, min(2, score))
    suggested = SIZE_NAMES[score]

    return {
        "mode": "intake",
        "status": "ok",
        "current": current,
        "suggested": suggested,
        "ux_heavy": ux_heavy,
        "domain": domain,
        "deliverable_count": deliverable_count,
        "reason": "; ".join(reasons) if reasons else "default M (no strong pulls)",
        "agreement": (current is None) or (current == suggested),
    }


# ---------- Runtime measurement ----------

# Tier thresholds; runtime OBSERVED size = highest tier whose threshold is met.
# Aligned with engagement-protocol §"Engagement size tier (S / M / L)".
THRESHOLDS = {
    # S thresholds — anything fitting all of these is S-eligible
    "S": {"max_specialists": 1, "max_files": 2, "max_loc": 50, "max_tasks": 0, "max_ui_surfaces": 0},
    # M — boundary
    "M": {"max_specialists": 3, "max_files": 10, "max_loc": 500, "max_tasks": 8, "max_ui_surfaces": 4},
    # L — anything above M is L
}


def count_executor_specialists(eng: Path) -> int:
    d = eng / "executor-reports"
    if not d.exists():
        return 0
    return len([f for f in d.glob("*.md") if f.is_file()])


def count_tasks(eng: Path) -> int:
    d = eng / "tasks"
    if not d.exists():
        return 0
    return len([f for f in d.glob("*.md") if f.is_file() and f.name != "INDEX.md"])


def count_ui_surfaces(eng: Path) -> int:
    """Distinct screens/{iter}/{theme}/{surface}.png count (across themes)."""
    d = eng / "screens"
    if not d.exists():
        return 0
    surfaces: set[str] = set()
    for png in d.rglob("*.png"):
        # Path: screens/iter-1/dark/dashboard.png → key = "dashboard"
        surfaces.add(png.stem)
    return len(surfaces)


def count_diff_files_loc(eng: Path) -> tuple[int, int]:
    """Parse handoff.md §1 Diff summary for files-changed and lines-added.

    Looks for output of `git diff --stat` style:
      ` 5 files changed, 234 insertions(+), 12 deletions(-)`

    Returns (files, loc_added). Returns (0, 0) if handoff missing or no §1.
    """
    handoff = eng / "handoff.md"
    if not handoff.exists():
        return 0, 0
    text = handoff.read_text(encoding="utf-8")
    # Capture §1 block
    block = re.search(
        r"^##\s*1\.\s*Diff\s*summary.*?(?=^##\s|\Z)",
        text, re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    if not block:
        return 0, 0
    body = block.group(0)
    m = re.search(r"(\d+)\s+files?\s+changed,\s+(\d+)\s+insertions?", body)
    if m:
        return int(m.group(1)), int(m.group(2))
    # Fallback: count `M file` / `A file` lines (one per file)
    file_lines = re.findall(r"^\s*[MADRT]\s+\S+", body, re.MULTILINE)
    return len(file_lines), 0


def count_deploy_crossed(eng: Path) -> bool:
    return (eng / "deploy-log.md").exists()


def runtime_observe(eng: Path) -> dict:
    """Measure current engagement state and decide observed tier."""
    meta = read_criteria_meta(eng)
    if not meta:
        return {
            "mode": "runtime", "status": "error", "current": None, "observed": None,
            "reason": "criteria.md missing or has no frontmatter",
        }

    current = (meta.get("size") or "M").upper()
    if current not in SIZE_ORDER:
        current = "M"
    ux_heavy = (meta.get("ux_heavy") or "false").lower()

    # Measure
    specialists = count_executor_specialists(eng)
    tasks = count_tasks(eng)
    ui_surfaces = count_ui_surfaces(eng)
    files, loc = count_diff_files_loc(eng)
    deploy = count_deploy_crossed(eng)

    measurements = {
        "specialists": specialists,
        "tasks": tasks,
        "ui_surfaces": ui_surfaces,
        "diff_files": files,
        "diff_loc_added": loc,
        "deploy_crossed": deploy,
        "ux_heavy": ux_heavy,
    }

    # Pick observed tier: highest threshold any measurement crosses
    observed_score = 0  # S
    triggered: list[str] = []

    s_t = THRESHOLDS["S"]
    m_t = THRESHOLDS["M"]

    # S → M boundary
    if specialists > s_t["max_specialists"]:
        observed_score = max(observed_score, 1)
        triggered.append(f"specialists={specialists} > S-cap {s_t['max_specialists']}")
    if files > s_t["max_files"]:
        observed_score = max(observed_score, 1)
        triggered.append(f"diff_files={files} > S-cap {s_t['max_files']}")
    if loc > s_t["max_loc"]:
        observed_score = max(observed_score, 1)
        triggered.append(f"loc_added={loc} > S-cap {s_t['max_loc']}")
    if tasks > s_t["max_tasks"]:
        observed_score = max(observed_score, 1)
        triggered.append(f"tasks={tasks} > S-cap {s_t['max_tasks']}")
    if ui_surfaces > s_t["max_ui_surfaces"]:
        observed_score = max(observed_score, 1)
        triggered.append(f"ui_surfaces={ui_surfaces} > S-cap {s_t['max_ui_surfaces']}")
    if ux_heavy in {"minor", "true"} and observed_score < 1:
        observed_score = 1
        triggered.append(f"ux_heavy={ux_heavy} → M floor")

    # M → L boundary
    if specialists > m_t["max_specialists"]:
        observed_score = 2
        triggered.append(f"specialists={specialists} > M-cap {m_t['max_specialists']}")
    if files > m_t["max_files"]:
        observed_score = 2
        triggered.append(f"diff_files={files} > M-cap {m_t['max_files']}")
    if loc > m_t["max_loc"]:
        observed_score = 2
        triggered.append(f"loc_added={loc} > M-cap {m_t['max_loc']}")
    if tasks > m_t["max_tasks"]:
        observed_score = 2
        triggered.append(f"tasks={tasks} > M-cap {m_t['max_tasks']}")
    if ui_surfaces > m_t["max_ui_surfaces"]:
        observed_score = 2
        triggered.append(f"ui_surfaces={ui_surfaces} > M-cap {m_t['max_ui_surfaces']}")
    if deploy:
        observed_score = 2
        triggered.append("deploy-log.md present (production deploy → L floor)")

    observed = SIZE_NAMES[observed_score]
    current_score = SIZE_ORDER[current]

    promote_needed = observed_score > current_score

    return {
        "mode": "runtime",
        "status": "ok",
        "current": current,
        "observed": observed,
        "promote": promote_needed,
        "measurements": measurements,
        "triggered": triggered,
        "reason": "; ".join(triggered) if triggered else f"all measurements within {current} caps",
    }


def auto_promote_apply(eng: Path, current: str, observed: str, reason: str) -> dict:
    """Apply auto-promote: rewrite frontmatter size, append scope-sync.md entry.

    Promote-only (S→M, M→L, S→L). Never demote. Idempotent.
    """
    if SIZE_ORDER.get(observed, -1) <= SIZE_ORDER.get(current, -1):
        return {"applied": False, "reason": "no promote needed (observed ≤ current)"}

    # 1. Rewrite criteria.md frontmatter (idempotent re-read so we don't clobber)
    crit = eng / "criteria.md"
    text = crit.read_text(encoding="utf-8")
    new_text, n = re.subn(
        r"(^size\s*:\s*)([SMLsml])\b",
        rf"\g<1>{observed}",
        text, count=1, flags=re.MULTILINE,
    )
    if n != 1:
        return {
            "applied": False,
            "reason": f"could not find/replace size: line in criteria.md (matched {n} times)",
        }
    crit.write_text(new_text, encoding="utf-8")

    # 2. Append scope-sync.md entry (create if missing)
    scope_sync = eng / "scope-sync.md"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    entry = (
        f"\n## Auto-promote — size {current} → {observed} — {ts}\n\n"
        f"**Trigger:** size-detect.py runtime measurements crossed tier threshold.\n\n"
        f"**Measurements:** {reason}\n\n"
        f"**Effect:** schema relaxations now reflect {observed}-tier rigour "
        f"(see engagement-protocol §Schema relaxations by tier). Lead acks via heartbeat.\n"
    )
    if scope_sync.exists():
        scope_sync.write_text(scope_sync.read_text(encoding="utf-8") + entry, encoding="utf-8")
    else:
        header = (
            "# Scope sync — auto-edits log\n\n"
            "This file records lead/secretary clarifications and size auto-promotions "
            "that did not require user touch (per engagement-protocol §criteria.md mutability rules).\n"
        )
        scope_sync.write_text(header + entry, encoding="utf-8")

    return {
        "applied": True,
        "from": current,
        "to": observed,
        "criteria_md_updated": True,
        "scope_sync_md_updated": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Engagement size tier detector + auto-promote")
    parser.add_argument("engagement", help="Path to engagement/ directory")
    parser.add_argument("--mode", choices=["intake", "runtime"], required=True)
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument(
        "--auto-promote", action="store_true",
        help="(runtime only) rewrite criteria.md size + append scope-sync.md entry",
    )
    args = parser.parse_args()

    eng = Path(args.engagement).resolve()
    if not eng.exists():
        print(f"ERROR: engagement directory not found: {eng}", file=sys.stderr)
        return 2

    if args.mode == "intake":
        result = intake_heuristic(eng)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            if result["status"] == "error":
                print(f"[ERROR] {result['reason']}")
                return 2
            agree = "MATCH" if result["agreement"] else "MISMATCH"
            print(
                f"Intake heuristic: current={result['current']!s:<5} suggested={result['suggested']:<5} {agree}"
            )
            print(f"  reason: {result['reason']}")
        return 0  # always advisory

    # runtime
    result = runtime_observe(eng)
    if result["status"] == "error":
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"[ERROR] {result['reason']}")
        return 2

    if args.auto_promote and result["promote"]:
        applied = auto_promote_apply(
            eng, result["current"], result["observed"], result["reason"],
        )
        result["auto_promote"] = applied

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        flag = "PROMOTE" if result["promote"] else "OK"
        print(
            f"Runtime size: current={result['current']:<2} observed={result['observed']:<2} {flag}"
        )
        if result["triggered"]:
            for t in result["triggered"]:
                print(f"  - {t}")
        if "auto_promote" in result:
            ap = result["auto_promote"]
            if ap.get("applied"):
                print(f"  → auto-promote applied: {ap['from']} → {ap['to']}")
            else:
                print(f"  → auto-promote skipped: {ap['reason']}")

    return 1 if result["promote"] else 0


if __name__ == "__main__":
    sys.exit(main())
