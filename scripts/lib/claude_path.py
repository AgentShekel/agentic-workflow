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
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional


def find_claude_cmd() -> Optional[str]:
    """Return a path to a claude executable safe for multiline argv, or None.

    Probes "claude", "claude.cmd", "claude.exe" in order; when the resolved
    entry is a Windows .CMD npm wrapper, resolves to the sibling claude.exe so
    multiline prompts survive argv passing.
    """
    for c in ("claude", "claude.cmd", "claude.exe"):
        p = shutil.which(c)
        if p:
            if Path(p).suffix.lower() == ".cmd":
                exe = (
                    Path(p).parent
                    / "node_modules"
                    / "@anthropic-ai"
                    / "claude-code"
                    / "bin"
                    / "claude.exe"
                )
                if exe.exists():
                    return str(exe)
            return p
    return None
