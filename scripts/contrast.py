#!/usr/bin/env python3
"""Deterministic WCAG 2.x contrast calculator for validator agents.

Validators that estimate contrast by eye misreport it (a 4.95:1 pair reported as 4.48:1 and
flagged critical, 2026-10-06 executable pilot). This script is the arithmetic; the agent's job
is to resolve which foreground sits on which background.

Usage (pairs are positional, foreground then background, any number of pairs):
  python contrast.py "#6b7280" "#1f2937"
  python contrast.py "#ffffff" "#2f9e44" --size 40 --weight 700
  python contrast.py "rgba(0,0,0,0.45)" "#ffffff"           # translucent fg composited over bg
  python contrast.py "#ffffff" "rgba(0,0,0,0.45)" --over "#ffffff"  # translucent bg needs --over
  python contrast.py "#707070" "#fff" "#1a1a1a" "#fff"      # two pairs

Output: one JSON object per pair, as a JSON list. `passes_aa` uses the large-text bar (3:1)
only when --size/--weight say the text is large (>= 24px, or >= 18.66px at weight >= 700);
without --size it reports both bars and leaves `large_text` null.
"""
from __future__ import annotations

import argparse
import json
import re
import sys

NAMED = {"white": "#ffffff", "black": "#000000", "transparent": "rgba(0,0,0,0)"}
HEX_RE = re.compile(r"^#?([0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})$", re.IGNORECASE)
RGB_RE = re.compile(r"^rgba?\(\s*([\d.]+%?)\s*[, ]\s*([\d.]+%?)\s*[, ]\s*([\d.]+%?)\s*(?:[,/]\s*([\d.]+%?)\s*)?\)$", re.IGNORECASE)


def parse(color: str) -> tuple[float, float, float, float]:
    """-> (r, g, b, a) with r,g,b in 0..255 and a in 0..1."""
    c = NAMED.get(color.strip().lower(), color.strip())
    m = HEX_RE.match(c)
    if m:
        h = m.group(1)
        if len(h) in (3, 4):
            h = "".join(ch * 2 for ch in h)
        vals = [int(h[i:i + 2], 16) for i in range(0, len(h), 2)]
        a = vals[3] / 255 if len(vals) == 4 else 1.0
        return float(vals[0]), float(vals[1]), float(vals[2]), a
    m = RGB_RE.match(c)
    if m:
        def chan(s: str) -> float:
            return float(s[:-1]) * 2.55 if s.endswith("%") else float(s)
        r, g, b = (chan(m.group(i)) for i in (1, 2, 3))
        a_s = m.group(4)
        a = 1.0 if a_s is None else (float(a_s[:-1]) / 100 if a_s.endswith("%") else float(a_s))
        if not all(0 <= v <= 255 for v in (r, g, b)) or not 0 <= a <= 1:
            raise ValueError(f"out of range: {color}")
        return r, g, b, a
    raise ValueError(f"unrecognised colour: {color!r} (use #hex, rgb(), rgba() or white/black)")


def composite(top, bottom) -> tuple[float, float, float, float]:
    """Alpha-composite `top` over an opaque `bottom`."""
    a = top[3]
    return (top[0] * a + bottom[0] * (1 - a), top[1] * a + bottom[1] * (1 - a),
            top[2] * a + bottom[2] * (1 - a), 1.0)


def luminance(c) -> float:
    def lin(v: float) -> float:
        s = v / 255
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2])


def to_hex(c) -> str:
    r, g, b = (round(v) for v in c[:3])
    return f"#{r:02x}{g:02x}{b:02x}"


def pair(fg_s: str, bg_s: str, over: str | None, size: float | None, weight: int | None) -> dict:
    bg = parse(bg_s)
    if bg[3] < 1:
        if over is None:
            raise ValueError(f"background {bg_s} is translucent; pass --over <opaque colour beneath it>")
        bg = composite(bg, parse(over))
    fg = composite(parse(fg_s), bg) if parse(fg_s)[3] < 1 else parse(fg_s)
    l1, l2 = sorted((luminance(fg), luminance(bg)), reverse=True)
    ratio = (l1 + 0.05) / (l2 + 0.05)
    large = None
    if size is not None:
        large = size >= 24 or (size >= 18.66 and (weight or 400) >= 700)
    bar = None if large is None else (3.0 if large else 4.5)
    return {
        "fg": fg_s, "bg": bg_s, "fg_resolved": to_hex(fg), "bg_resolved": to_hex(bg),
        "ratio": round(ratio, 2), "ratio_exact": round(ratio, 4),
        "aa_normal_text": ratio >= 4.5, "aa_large_text": ratio >= 3.0, "aa_non_text": ratio >= 3.0,
        "aaa_normal_text": ratio >= 7.0,
        "large_text": large, "applicable_bar": bar,
        "passes_aa": None if bar is None else ratio >= bar,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("colors", nargs="+", help="fg bg [fg bg ...]")
    ap.add_argument("--over", default=None, help="opaque colour beneath a translucent background")
    ap.add_argument("--size", type=float, default=None, help="font size in px (enables the large-text decision)")
    ap.add_argument("--weight", type=int, default=None, help="font weight, e.g. 400 or 700")
    a = ap.parse_args(argv)
    if len(a.colors) % 2:
        print(json.dumps({"error": "colours must come in fg/bg pairs"}))
        return 2
    try:
        out = [pair(a.colors[i], a.colors[i + 1], a.over, a.size, a.weight) for i in range(0, len(a.colors), 2)]
    except ValueError as e:
        print(json.dumps({"error": str(e)}))
        return 2
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
