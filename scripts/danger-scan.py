#!/usr/bin/env python3
"""Scan engagement diff/artefacts for dangerous operations requiring user OK.

Detects operations with heavy / irreversible consequences:
  - SQL: DROP TABLE, DROP COLUMN, TRUNCATE, DELETE FROM without WHERE
  - Migrations with empty / NotImplementedError down()
  - Git: force-push to main/master/release
  - Filesystem: rm -rf on shared paths, recursive bulk delete
  - Deploy: prod deploy commands without explicit ack
  - Secrets: rotation/deletion calls
  - Infra: terraform destroy, kubectl delete on prod ns

Output is a list of detected operations with severity. Lead must surface each
to user with explicit OK before proceeding. Director rejects handoff that lists
dangerous ops in §1 diff without corresponding user-OK entries in scope-sync.md.

Usage:
  python ~/.claude/scripts/danger-scan.py --diff "$(git diff main..HEAD)"
  python ~/.claude/scripts/danger-scan.py --diff-file /tmp/diff.patch
  python ~/.claude/scripts/danger-scan.py --engagement engagement/

Exit codes:
  0 — no dangerous operations detected
  1 — dangerous operations found (lead must coordinate user OK)
  2 — invocation error
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
import subprocess
from pathlib import Path

# Each rule: pattern (regex on diff text), severity, kind, fix-message.
RULES = [
    # SQL — schema destruction
    {
        "id": "sql-drop-table",
        "pattern": r"(?i)\bDROP\s+TABLE\b(?!\s+IF\s+NOT\s+EXISTS)",
        "severity": "critical",
        "kind": "data-loss",
        "msg": "DROP TABLE — irreversible data loss. Requires user OK + verified backup before apply.",
    },
    {
        "id": "sql-drop-column",
        "pattern": r"(?i)\bALTER\s+TABLE\b[^;]*\bDROP\s+COLUMN\b",
        "severity": "critical",
        "kind": "data-loss",
        "msg": "DROP COLUMN — column data deleted. Requires user OK; consider a deprecation window before drop.",
    },
    {
        "id": "sql-truncate",
        "pattern": r"(?i)\bTRUNCATE\s+(?:TABLE\s+)?\w+",
        "severity": "critical",
        "kind": "data-loss",
        "msg": "TRUNCATE — clears table contents. Requires user OK.",
    },
    {
        "id": "sql-delete-without-where",
        # DELETE FROM <name> not followed by WHERE on the same statement
        "pattern": r"(?i)\bDELETE\s+FROM\s+\w+(?:\s*\.\s*\w+)?\s*(?:RETURNING|;|$|\))(?!.*\bWHERE\b)",
        "severity": "high",
        "kind": "bulk-delete",
        "msg": "DELETE FROM without WHERE — wipes whole table. Add WHERE or surface to user.",
    },
    {
        "id": "sql-alter-column-lossy",
        "pattern": r"(?i)\bALTER\s+(?:TABLE\s+\w+\s+)?ALTER\s+COLUMN\b[^;]*\bTYPE\s+(?:varchar\s*\(\s*\d{1,2}\s*\)|int(?:eger)?|smallint)",
        "severity": "high",
        "kind": "type-narrowing",
        "msg": "ALTER COLUMN TYPE narrowing — possible lossy cast. Requires user OK + per-row safety check.",
    },
    # Migration sloppiness
    {
        "id": "migration-empty-down",
        "pattern": r"def\s+down(?:grade)?\s*\([^)]*\)\s*(?:->\s*\w+\s*)?:\s*(?:pass\b|\.\.\.|raise\s+NotImplementedError|return\s*$)",
        "severity": "high",
        "kind": "no-rollback",
        "msg": "Migration down() is empty / not implemented. No rollback path = ACCEPT becomes irreversible.",
    },
    # Git destructive
    {
        "id": "git-force-push",
        "pattern": r"git\s+push\s+(?:[^&|;\n]*\s)?(?:--force\b|-f\b|--force-with-lease\b)",
        "severity": "critical",
        "kind": "history-rewrite",
        "msg": "Force-push detected. Rewrites remote history; teammates must re-clone. Requires user OK; never to main/master.",
    },
    {
        "id": "git-reset-hard",
        "pattern": r"git\s+reset\s+(?:--hard|--keep)\s+(?:HEAD|origin|main|master)",
        "severity": "high",
        "kind": "history-rewrite",
        "msg": "git reset --hard — discards uncommitted work + history. Confirm intent.",
    },
    # Filesystem
    {
        "id": "fs-rm-rf-shared",
        "pattern": r"\brm\s+(?:-rf?|-fr|--recursive[\s-]+--force)\b\s+(?:[/\"']?(?:/|~|\$HOME|node_modules/\.\.|\.\.))",
        "severity": "critical",
        "kind": "fs-recursive-delete",
        "msg": "rm -rf on parent / home / root path. Requires user OK + dry-run first.",
    },
    # Deploy
    {
        "id": "terraform-destroy",
        "pattern": r"\bterraform\s+(?:destroy|apply\s+[^|;\n]*-destroy)\b",
        "severity": "critical",
        "kind": "infra-tear-down",
        "msg": "terraform destroy — tears down infrastructure. Always user OK.",
    },
    {
        "id": "kubectl-delete-prod-ns",
        "pattern": r"\bkubectl\s+delete\s+\w+\s+[^|;\n]*--namespace[\s=](?:prod|production|main)\b",
        "severity": "critical",
        "kind": "k8s-delete",
        "msg": "kubectl delete in prod namespace. Always user OK.",
    },
    {
        "id": "deploy-prod-direct",
        # very broad heuristic; surface for review
        "pattern": r"(?i)\b(?:vercel\s+--prod|fly\s+deploy\s+(?:--prod|--strategy[\s=]immediate)|railway\s+up\s+--service\s+\w+\s+--env\s+production|gh\s+release\s+create)\b",
        "severity": "high",
        "kind": "production-deploy",
        "msg": "Production deploy command detected. Confirm criteria.md authorises this deploy; otherwise user OK before run.",
    },
    # Secrets
    {
        "id": "secret-rotation-explicit",
        "pattern": r"(?i)\b(?:rotate_secret|revoke_token|delete_credential|aws\s+secretsmanager\s+(?:rotate-secret|delete-secret)|gh\s+secret\s+remove)\b",
        "severity": "high",
        "kind": "secret-rotation",
        "msg": "Secret rotation/deletion. Requires user OK + downstream consumer notification plan.",
    },
    # Package publishing
    {
        "id": "package-publish",
        "pattern": r"(?i)\b(?:npm\s+publish(?!.*--dry-run)|yarn\s+publish|pnpm\s+publish|twine\s+upload(?!.*--repository\s+testpypi))\b",
        "severity": "high",
        "kind": "public-publish",
        "msg": "Package publish to public registry — irreversible (cannot fully unpublish). Requires user OK.",
    },
    # Bulk file delete (heuristic on diff: many - lines with file removals)
    # This rule fires from --engagement mode where we count actual deletions.
]


def find_in_text(text: str) -> list[dict]:
    """Run all regex rules against text. Return list of findings."""
    findings = []
    lines = text.splitlines()
    for rule in RULES:
        for i, line in enumerate(lines, 1):
            if re.search(rule["pattern"], line):
                findings.append({
                    "id": rule["id"],
                    "kind": rule["kind"],
                    "severity": rule["severity"],
                    "msg": rule["msg"],
                    "line": i,
                    "snippet": line.strip()[:200],
                })
    return findings


def bulk_delete_check(diff_text: str, threshold: int = 25) -> list[dict]:
    """Heuristic: count files removed entirely (deleted file headers in diff)."""
    deleted_files = re.findall(r"^diff --git a/(\S+) b/\S+\ndeleted file mode", diff_text, re.MULTILINE)
    if len(deleted_files) >= threshold:
        return [{
            "id": "fs-bulk-delete",
            "kind": "bulk-delete",
            "severity": "high",
            "msg": f"{len(deleted_files)} files deleted in this change — bulk-delete pattern. Surface list to user before merge.",
            "line": 0,
            "snippet": f"deleted_files[:5]={deleted_files[:5]}",
        }]
    return []


def scan_engagement(eng_path: Path) -> list[dict]:
    """Aggregate diff content from engagement and scan."""
    findings: list[dict] = []
    handoff = eng_path / "handoff.md"
    diff_text = ""
    if handoff.exists():
        # §1 Diff summary often pastes git output — scan it
        diff_text = handoff.read_text(encoding="utf-8")
    # Also try git diff in CWD against main
    try:
        r = subprocess.run(
            ["git", "diff", "main..HEAD"],
            capture_output=True, text=True, timeout=30,
            cwd=eng_path.parent if eng_path.parent.exists() else None,
        )
        if r.returncode == 0:
            diff_text += "\n\n" + r.stdout
    except Exception:
        pass

    findings.extend(find_in_text(diff_text))
    findings.extend(bulk_delete_check(diff_text))

    # Also walk specs/ and tasks/ for migration files
    for sub in ["specs", "tasks", "engagement/specs", "engagement/tasks"]:
        d = eng_path / sub
        if d.is_dir():
            for f in d.rglob("*.py"):
                findings.extend([{**fnd, "file": str(f)} for fnd in find_in_text(f.read_text(encoding="utf-8", errors="replace"))])
            for f in d.rglob("*.sql"):
                findings.extend([{**fnd, "file": str(f)} for fnd in find_in_text(f.read_text(encoding="utf-8", errors="replace"))])

    return findings


def main() -> int:
    p = argparse.ArgumentParser(description="Scan for dangerous operations")
    p.add_argument("--diff", help="Diff text passed inline")
    p.add_argument("--diff-file", help="Path to a file containing diff text")
    p.add_argument("--engagement", help="Path to engagement/ directory (scan handoff + git diff + specs/tasks)")
    p.add_argument("--json", action="store_true", help="Output JSON")
    args = p.parse_args()

    if not (args.diff or args.diff_file or args.engagement):
        print("ERROR: provide --diff TEXT, --diff-file PATH, or --engagement PATH", file=sys.stderr)
        return 2

    findings: list[dict] = []
    if args.diff:
        findings.extend(find_in_text(args.diff))
        findings.extend(bulk_delete_check(args.diff))
    elif args.diff_file:
        text = Path(args.diff_file).read_text(encoding="utf-8")
        findings.extend(find_in_text(text))
        findings.extend(bulk_delete_check(text))
    elif args.engagement:
        eng = Path(args.engagement)
        if not eng.exists():
            print(f"ERROR: engagement path not found: {eng}", file=sys.stderr)
            return 2
        findings.extend(scan_engagement(eng))

    # Deduplicate by (id + line + file)
    seen = set()
    unique = []
    for f in findings:
        key = (f["id"], f.get("line", 0), f.get("file", ""), f.get("snippet", ""))
        if key not in seen:
            seen.add(key)
            unique.append(f)

    crit = sum(1 for f in unique if f["severity"] == "critical")
    high = sum(1 for f in unique if f["severity"] == "high")

    if args.json:
        print(json.dumps({
            "status": "fail" if unique else "pass",
            "critical": crit,
            "high": high,
            "findings": unique,
        }, ensure_ascii=False, indent=2))
    else:
        if not unique:
            print("VERDICT: PASS — no dangerous operations detected.")
            return 0
        print(f"DANGEROUS OPERATIONS DETECTED — {crit} critical, {high} high")
        print()
        for f in unique:
            mark = "[CRIT]" if f["severity"] == "critical" else "[HIGH]"
            loc = f"line {f.get('line')}" if f.get("line") else ""
            file_info = f" in {f['file']}" if f.get("file") else ""
            print(f"{mark} {f['id']}{file_info} {loc}")
            print(f"       {f['msg']}")
            if f.get("snippet"):
                print(f"       snippet: {f['snippet']}")
            print()
        print("VERDICT: FAIL — surface each to user. Lead must obtain explicit OK in scope-sync.md before proceeding.")

    return 1 if unique else 0


if __name__ == "__main__":
    sys.exit(main())
