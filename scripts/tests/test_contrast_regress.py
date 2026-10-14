#!/usr/bin/env python3
"""Regression for scripts/contrast.py. Expected ratios are independent WCAG 2.x values (the
pairs the 2026-10-06 executable pilot showed a haiku validator misreporting by eye)."""
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "contrast.py"


def run(*args):
    r = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=False)
    return r.returncode, json.loads(r.stdout)


CASES = [
    (("#ffffff", "#000000"), 21.0, None),
    (("#6b7280", "#1f2937"), 3.04, None),
    (("#ffffff", "#2f9e44"), 3.45, None),
    (("#707070", "#ffffff"), 4.95, None),
    (("#4b5563", "#ffffff"), 7.56, None),
    (("#111827", "#93c5fd"), 9.84, None),
    (("#fff", "#2f9e44"), 3.45, None),                        # short hex
    (("white", "rgb(47, 158, 68)"), 3.45, None),              # named + rgb()
    (("#ffffff", "rgba(0,0,0,0.45)", "--over", "#ffffff"), 3.36, None),   # scrim over white
    (("rgba(0,0,0,0.45)", "#ffffff"), 3.36, None),            # translucent fg composited
]


def main() -> int:
    bad = 0
    for args, want, _ in CASES:
        rc, out = run(*args)
        got = out[0]["ratio"] if rc == 0 else None
        ok = rc == 0 and abs(got - want) < 0.011
        bad += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] {' '.join(args)} -> {got} (want {want})")
    # large-text decision
    for size, weight, want_large, want_pass in [(40, 700, True, True), (14, 400, False, False),
                                                (19, 700, True, True), (19, 400, False, False)]:
        rc, out = run("#ffffff", "#2f9e44", "--size", str(size), "--weight", str(weight))
        ok = rc == 0 and out[0]["large_text"] is want_large and out[0]["passes_aa"] is want_pass
        bad += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] 3.45:1 at {size}px/{weight}: large={out[0]['large_text']} passes={out[0]['passes_aa']}")
    # several pairs in one call, and errors
    rc, out = run("#707070", "#fff", "#1a1a1a", "#fff")
    ok = rc == 0 and [p["ratio"] for p in out] == [4.95, 17.4]
    bad += not ok
    print(f"[{'PASS' if ok else 'FAIL'}] two pairs -> {[p['ratio'] for p in out] if rc == 0 else out}")
    for args in (("#fff",), ("#ffffff", "rgba(0,0,0,.5)"), ("#ggg", "#fff")):
        rc, out = run(*args)
        ok = rc == 2 and "error" in out
        bad += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] error on {args}: rc={rc}")
    total = len(CASES) + 4 + 1 + 3
    print(f"{total - bad}/{total} checks passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
