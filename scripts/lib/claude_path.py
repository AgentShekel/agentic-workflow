"""Shared claude CLI path resolver for the LangGraph engines.

Extracted 2026-05-29 from three near-duplicate copies in adversary_lg.py /
validator_lg.py / engagement_lg.py. The copies had drifted (adversary_lg's
variant probed only "claude"; the others probed claude/.cmd/.exe) and the same
Windows .CMD bug had to be patched in three places — exactly the copy-paste
hazard this module removes. Future changes to claude resolution live here only.

Windows: `shutil.which("claude")` returns the npm `claude.CMD` wrapper, which
truncates multiline argv at the first newline (CMD line-parsing semantics),
silently mangling multi-line prompts. When the resolved entry is a .CMD wrapper,
resolve to the underlying `claude.exe` via the npm wrapper layout. Unix/macOS
unaffected (no .CMD is ever returned).

Resolution order (2026-06-01, dispatch-gap close):
  1. `CLAUDE_CLI_PATH` / `CLAUDE_CLI` env override — operator escape hatch that
     survives any PATH stripping.
  2. `shutil.which()` — the fast path when claude is on PATH.
  3. Fallback probe of known install locations — a recursive `claude -p`
     subprocess launched from inside an agent session can inherit a STRIPPED
     PATH that omits the npm / ~/.local/bin dirs (this is what made
     engagement_lg.py die with "claude CLI not found in PATH" on 2026-05-28 even
     though the binary was installed). Probing the canonical install dirs makes
     discovery independent of the inherited PATH, which is the keystone that lets
     validator_lg / adversary_lg actually dispatch in the engagement runtime.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional


def _prefer_exe(p: Path) -> str:
    """On Windows, swap an npm `.cmd` wrapper for its sibling `claude.exe`
    (multiline-argv safe). Everything else is returned as-is."""
    if p.suffix.lower() == ".cmd":
        exe = (
            p.parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
        )
        if exe.exists():
            return str(exe)
    return str(p)


def _fallback_locations() -> list[Path]:
    """Canonical install dirs to probe when claude is not on PATH. Order =
    most-specific (multiline-safe .exe) first."""
    home = Path.home()
    return [
        # Windows npm global — the .exe under the wrapper (what `which` resolves to)
        home / "AppData" / "Roaming" / "npm" / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe",
        # Windows native installer
        home / ".local" / "bin" / "claude.exe",
        # Unix / macOS native installer
        home / ".local" / "bin" / "claude",
        # macOS Homebrew + common Unix prefixes
        Path("/opt/homebrew/bin/claude"),
        Path("/usr/local/bin/claude"),
        # Unix npm global layouts
        home / ".npm-global" / "bin" / "claude",
        Path("/usr/local/lib/node_modules/@anthropic-ai/claude-code/bin/claude"),
    ]


def find_claude_cmd() -> Optional[str]:
    """Return a path to a claude executable safe for multiline argv, or None.

    Order: env override → PATH (`which`) → fallback probe of known install dirs.
    When a resolved entry is a Windows .CMD npm wrapper, resolves to the sibling
    claude.exe so multiline prompts survive argv passing.
    """
    # 1. Explicit operator override — survives any PATH stripping.
    env = os.environ.get("CLAUDE_CLI_PATH") or os.environ.get("CLAUDE_CLI")
    if env and Path(env).exists():
        return _prefer_exe(Path(env))

    # 2. PATH lookup (fast path when claude is on PATH).
    for c in ("claude", "claude.cmd", "claude.exe"):
        p = shutil.which(c)
        if p:
            return _prefer_exe(Path(p))

    # 3. Fallback: probe canonical install dirs (inherited PATH may be stripped
    #    in a nested-subprocess launch — the 2026-05-28 "claude not found").
    for cand in _fallback_locations():
        try:
            if cand.exists():
                return str(cand)
        except OSError:
            continue
    return None
