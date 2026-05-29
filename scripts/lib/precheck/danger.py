"""Dangerous-operations authorization check.

One check lives here:
  - check_danger_scan: delegate to danger-scan.py; surface dangerous ops
    requiring user OK and verify each finding has a corresponding entry in
    scope-sync.md.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .common import run


def check_danger_scan(eng: Path, scripts_dir: Path) -> dict:
    """Run danger-scan.py — surface dangerous ops requiring user OK."""
    code, out = run([sys.executable, str(scripts_dir / "danger-scan.py"), "--engagement", str(eng), "--json"])
    try:
        data = json.loads(out)
        findings = data.get("findings", [])
        if not findings:
            return {"name": "danger-scan", "status": "pass", "detail": "no dangerous operations detected"}

        # Check whether each finding has a corresponding user-OK in scope-sync.md
        scope_sync = eng / "scope-sync.md"
        ok_text = scope_sync.read_text(encoding="utf-8") if scope_sync.exists() else ""

        unauthorized = []
        for f in findings:
            fid = f.get("id", "")
            # Match by operation id appearing in scope-sync user-OK section
            if fid not in ok_text:
                unauthorized.append(fid)

        if unauthorized:
            return {
                "name": "danger-scan",
                "status": "fail",
                "detail": f"dangerous ops without user OK: {sorted(set(unauthorized))}",
                "fix": "Surface each to user via director-mediated escalation; record OK in scope-sync.md per engagement-protocol §dangerous-operations.",
            }
        return {"name": "danger-scan", "status": "pass", "detail": f"{len(findings)} dangerous ops found, all have user-OK entries"}
    except json.JSONDecodeError:
        return {"name": "danger-scan", "status": "fail", "detail": f"danger-scan script error: {out[:200]}"}
