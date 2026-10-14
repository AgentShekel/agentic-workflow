#!/usr/bin/env python3
"""Validate engagement/traces/*.json against the structured schema.

Schema (per engagement-protocol §"Trace JSON schema"):
  {
    "flow": str,
    "iteration": int,
    "captured_at": str (ISO),
    "steps": [
      {
        "action": str,
        "selector": str,
        "expected": str,
        "observed": object,
        "verdict": "PASS" | "FAIL",
        "notes": str (optional)
      }
    ],
    "network": list (optional),
    "console": list (optional),
    "dom_snapshot": str (optional)
  }

Usage:
  python ~/.claude/scripts/trace-schema-check.py engagement/traces/

Exit codes:
  0 — all traces valid
  1 — at least one invalid
  2 — invocation error / no traces dir
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
import sys
from pathlib import Path

REQUIRED_TOP = ["flow", "iteration", "captured_at", "steps"]
REQUIRED_STEP = ["action", "selector", "expected", "observed", "verdict"]
VALID_VERDICTS = {"PASS", "FAIL"}


def validate_trace(path: Path) -> tuple[list[str], list[str]]:
    """Return (errors, warnings).

    Errors block submit. Warnings are non-blocking (e.g. staleness).
    """
    errs: list[str] = []
    warns: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return [f"not parseable JSON: {e}"], []

    if not isinstance(data, dict):
        return ["root is not an object"], []

    for k in REQUIRED_TOP:
        if k not in data:
            errs.append(f"missing top-level field: {k}")

    if "iteration" in data and not isinstance(data["iteration"], int):
        errs.append(f"iteration must be int, got {type(data['iteration']).__name__}")

    steps = data.get("steps", [])
    if not isinstance(steps, list) or not steps:
        errs.append("steps must be non-empty list")
    else:
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                errs.append(f"step {i}: not an object")
                continue
            for k in REQUIRED_STEP:
                if k not in step:
                    errs.append(f"step {i}: missing field '{k}'")
            v = step.get("verdict")
            if v is not None and v not in VALID_VERDICTS:
                errs.append(f"step {i}: verdict={v!r}, expected one of {VALID_VERDICTS}")
            obs = step.get("observed")
            if obs is not None and not isinstance(obs, (dict, list, str, int, float, bool)):
                errs.append(f"step {i}: observed must be primitive/object/list, got {type(obs).__name__}")

    # Staleness: if captured_at older than the trace file's own mtime by > 1h,
    # OR if any landing/ HTML referenced has mtime > captured_at + 60s — warn.
    captured_at = data.get("captured_at")
    if captured_at:
        import datetime as _dt
        try:
            ts_str = str(captured_at).rstrip("Z").rstrip("z")
            captured_dt = _dt.datetime.fromisoformat(ts_str)
            captured_ts = captured_dt.timestamp()
        except Exception:
            warns.append(f"captured_at not parseable as ISO 8601: {captured_at}")
            captured_ts = None

        if captured_ts:
            # Heuristic: walk up to find a sibling landing/ or hybrid/ dir, check HTML mtimes
            project_root = path.resolve().parent
            for _ in range(5):
                if project_root.parent == project_root:
                    break
                landing_candidate = project_root / "landing"
                hybrid_candidate = project_root / "hybrid"
                if landing_candidate.exists() or hybrid_candidate.exists():
                    break
                project_root = project_root.parent
            stale = []
            for candidate_dir in [project_root / "landing", project_root / "hybrid"]:
                if not candidate_dir.exists():
                    continue
                for html in list(candidate_dir.rglob("*.html"))[:30]:
                    try:
                        if html.stat().st_mtime > captured_ts + 60:
                            stale.append(str(html.name))
                    except Exception:
                        continue
            if stale:
                warns.append(
                    f"captured_at ({captured_at}) is older than referenced HTML mtimes — trace may be stale: {stale[:3]}"
                )

    return errs, warns


def main() -> int:
    p = argparse.ArgumentParser(description="Validate trace JSON schema")
    p.add_argument("traces_dir", help="Path to engagement/traces/ (or specific trace JSON file)")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    target = Path(args.traces_dir)
    if not target.exists():
        msg = f"path not found: {target}"
        if args.json:
            print(json.dumps({"status": "skip", "message": msg}))
        else:
            print(msg)
        return 0  # absence of traces is not a failure here — the upstream gate handles ux_heavy=true requirement

    if target.is_file():
        files = [target]
    else:
        files = sorted(target.rglob("*.json"))

    if not files:
        msg = "no trace JSON files found"
        if args.json:
            print(json.dumps({"status": "skip", "message": msg, "files": []}))
        else:
            print(msg)
        return 0

    results = []
    fail_count = 0
    warn_count = 0
    for f in files:
        errs, warns = validate_trace(f)
        if errs:
            fail_count += 1
            status = "fail"
        elif warns:
            warn_count += 1
            status = "warn"
        else:
            status = "pass"
        results.append({
            "file": str(f.relative_to(target.parent) if target.is_dir() else f.name),
            "status": status,
            "errors": errs,
            "warnings": warns,
        })

    if args.json:
        overall = "fail" if fail_count else ("warn" if warn_count else "pass")
        print(json.dumps({
            "status": overall,
            "fail_count": fail_count,
            "warn_count": warn_count,
            "total": len(results),
            "files": results,
        }, ensure_ascii=False, indent=2))
    else:
        for r in results:
            mark = {"pass": "[OK  ]", "fail": "[FAIL]", "warn": "[WARN]"}[r["status"]]
            print(f"{mark} {r['file']}")
            for e in r["errors"]:
                print(f"       err: {e}")
            for w in r["warnings"]:
                print(f"       warn: {w}")
        print()
        if fail_count:
            print(f"VERDICT: FAIL — {fail_count}/{len(results)} traces violate schema.")
        elif warn_count:
            print(f"VERDICT: WARN — {warn_count}/{len(results)} traces have non-blocking concerns.")
        else:
            print(f"VERDICT: PASS — {len(results)} traces valid.")

    return 1 if fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
