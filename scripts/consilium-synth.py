#!/usr/bin/env python3
"""Consilium synthesizer — aggregates adversary outputs into a single report.

Reads engagement/validation-outputs/{role}-iter-{N}-*.json files produced by
adversary_lg.py, computes agreement / disagreement / dedup, writes
engagement/consilium-summary.md (machine-aggregated; director writes verdict
on top of this aggregation, see director-acceptance-protocol skill).

Aggregation rules:
  - Convergent finding: ≥3 reviewers report same issue (text similarity > 0.6).
  - Cross-family disagreement: peer-opus says satisfied, codex-blind/informed
    says rework_required (or vice versa).
  - Naive-layer catch: Sonnet/Haiku found something none of stronger reviewers
    flagged → "obvious miss" signal.
  - Suspicious-too-clean: at least one reviewer flagged this; require director
    review even if others said satisfied.

Usage:
  python ~/.claude/scripts/consilium-synth.py engagement/
  python ~/.claude/scripts/consilium-synth.py engagement/ --iter 2
  python ~/.claude/scripts/consilium-synth.py engagement/ --json

Exit codes:
  0 — synthesis completed (regardless of verdict aggregation)
  1 — no adversary outputs found for current iteration
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
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

REVIEWER_TIERS = {
    "peer-opus": "peer",
    "codex-blind": "cross-family",
    "codex-informed": "cross-family",
    "sonnet-scoped": "naive",
    "haiku-scoped": "naive",
}

SEVERITY_ORDER = {"critical": 3, "major": 2, "minor": 1}


def read_iter_counter(eng: Path) -> int:
    counter = eng / "iteration"
    if counter.exists():
        try:
            return int(counter.read_text(encoding="utf-8").strip())
        except Exception:
            pass
    return 1


def load_outputs(eng: Path, iter_n: int) -> list[dict]:
    """Load latest output per role for the given iteration."""
    outputs_dir = eng / "validation-outputs"
    if not outputs_dir.exists():
        return []
    pattern = re.compile(r"^(?P<role>[\w-]+?)-iter-(?P<iter>\d+)-(?P<ts>[\d\w]+)\.json$")
    by_role: dict[str, tuple[str, dict]] = {}
    for f in outputs_dir.glob("*.json"):
        m = pattern.match(f.name)
        if not m:
            continue
        if int(m.group("iter")) != iter_n:
            continue
        role = m.group("role")
        if role not in REVIEWER_TIERS:
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        ts = m.group("ts")
        prior = by_role.get(role)
        if prior is None or ts > prior[0]:
            by_role[role] = (ts, data)
    return [{"role": role, "data": data} for role, (_, data) in by_role.items()]


def text_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def normalize_path(path: str) -> str:
    """Normalize evidence path for clustering: strip line numbers, normalize separators."""
    if not path:
        return ""
    # Strip :line:col suffixes
    p = re.sub(r":\d+(?::\d+)?$", "", path.strip())
    # Normalize separators
    p = p.replace("\\", "/").lower()
    return p


def path_cluster_key(path: str) -> str:
    """Return clustering key for a finding's evidence_path.

    Two findings with the same key are likely the same issue regardless of
    issue-text wording.
    """
    norm = normalize_path(path)
    if not norm:
        return ""
    # Use the file path (without line) as cluster key
    return norm


def cluster_findings(
    outputs: list[dict],
    intra_path_threshold: float = 0.7,
    cross_path_threshold: float = 0.85,
) -> list[dict]:
    """Two-stage cluster of findings across reviewers.

    Stage 1: group by evidence_path (normalized — same file likely same issue).
              Within each path-group, dedup by issue-text similarity at intra_path_threshold (lenient).

    Stage 2: across path-groups, only merge if BOTH path-keys empty AND issue
              text is very-near-identical (cross_path_threshold) — handles findings
              that lack evidence_path but describe the same thing.

    Stage 3: leave the rest as separate findings (don't over-merge by lexical
              similarity alone — that was the original v1 bug).

    Returns list of clusters with metadata.
    """
    items = []
    for o in outputs:
        role = o["role"]
        for f in o["data"].get("findings", []):
            items.append({"role": role, **f})

    # Stage 1: bucket by path-cluster-key
    by_path_key: dict[str, list[list[dict]]] = {}
    for item in items:
        key = path_cluster_key(item.get("evidence_path", ""))
        buckets = by_path_key.setdefault(key, [])
        placed = False
        for bucket in buckets:
            # Within same path, lenient similarity merging
            sample_issue = bucket[0].get("issue", "")
            if text_similarity(item.get("issue", ""), sample_issue) >= intra_path_threshold:
                bucket.append(item)
                placed = True
                break
        if not placed:
            buckets.append([item])

    # Flatten Stage 1 buckets into clusters
    stage1_clusters: list[list[dict]] = []
    for buckets in by_path_key.values():
        stage1_clusters.extend(buckets)

    # Stage 2: only consider merging across no-path-key clusters with very-strict text similarity
    no_path_clusters = [c for c in stage1_clusters if not path_cluster_key(c[0].get("evidence_path", ""))]
    has_path_clusters = [c for c in stage1_clusters if path_cluster_key(c[0].get("evidence_path", ""))]

    merged_no_path: list[list[dict]] = []
    for cluster in no_path_clusters:
        placed = False
        for existing in merged_no_path:
            if text_similarity(cluster[0].get("issue", ""), existing[0].get("issue", "")) >= cross_path_threshold:
                existing.extend(cluster)
                placed = True
                break
        if not placed:
            merged_no_path.append(cluster)

    final_clusters = has_path_clusters + merged_no_path

    summarized = []
    for cluster in final_clusters:
        roles = sorted({c["role"] for c in cluster})
        sevs = [c.get("severity", "minor").lower() for c in cluster]
        max_sev = max(sevs, key=lambda s: SEVERITY_ORDER.get(s, 0))
        summarized.append({
            "issue": cluster[0].get("issue", ""),
            "evidence_path": cluster[0].get("evidence_path", ""),
            "max_severity": max_sev,
            "found_by": roles,
            "fix_hint": cluster[0].get("fix_hint", ""),
            "all_descriptions": [c.get("issue", "") for c in cluster],
            "cluster_size": len(cluster),
        })
    summarized.sort(
        key=lambda c: (-SEVERITY_ORDER.get(c["max_severity"], 0), -len(c["found_by"])),
    )
    return summarized


def compute_similarity_matrix(outputs: list[dict]) -> list[dict]:
    """Pairwise similarity for ALL findings — transparency aid for director.

    Director can scan this to decide if any two findings the synth left as
    separate are actually the same issue (or vice versa).
    """
    items = []
    for o in outputs:
        role = o["role"]
        for i, f in enumerate(o["data"].get("findings", [])):
            items.append({
                "id": f"{role}#{i}",
                "role": role,
                "issue": f.get("issue", ""),
                "evidence_path": f.get("evidence_path", ""),
            })
    pairs = []
    for i, a in enumerate(items):
        for b in items[i + 1:]:
            sim = text_similarity(a["issue"], b["issue"])
            same_path = (
                normalize_path(a["evidence_path"]) == normalize_path(b["evidence_path"])
                and a["evidence_path"]
            )
            # Only surface non-trivial pairs
            if sim >= 0.4 or same_path:
                pairs.append({
                    "a_id": a["id"],
                    "b_id": b["id"],
                    "issue_similarity": round(sim, 2),
                    "same_evidence_path": bool(same_path),
                })
    pairs.sort(key=lambda p: -p["issue_similarity"])
    return pairs


def detect_disagreements(outputs: list[dict]) -> list[dict]:
    """Pairs of reviewers with conflicting verdicts (satisfied vs rework_required)."""
    by_role = {o["role"]: o["data"].get("verdict", "") for o in outputs}
    disagreements = []
    roles = list(by_role.keys())
    for i, ra in enumerate(roles):
        for rb in roles[i + 1:]:
            va, vb = by_role[ra], by_role[rb]
            if {va, vb} == {"satisfied", "rework_required"}:
                # Cross-family-vs-Anthropic disagreement is most interesting
                ta, tb = REVIEWER_TIERS.get(ra), REVIEWER_TIERS.get(rb)
                kind = "cross-family" if {ta, tb} == {"peer", "cross-family"} else "intra-family"
                disagreements.append({
                    "reviewer_a": ra, "verdict_a": va,
                    "reviewer_b": rb, "verdict_b": vb,
                    "kind": kind,
                })
    return disagreements


def detect_naive_only_catches(clusters: list[dict]) -> list[dict]:
    """Findings that only Sonnet/Haiku flagged; stronger reviewers missed."""
    catches = []
    for c in clusters:
        tiers = {REVIEWER_TIERS.get(r) for r in c["found_by"]}
        if tiers and tiers.issubset({"naive"}):
            catches.append(c)
    return catches


def detect_suspicious_too_clean(outputs: list[dict]) -> list[str]:
    return [
        o["role"] for o in outputs
        if o["data"].get("verdict") == "suspicious_too_clean"
    ]


def determine_aggregate_verdict(
    outputs: list[dict],
    convergent: list[dict],
    disagreements: list[dict],
    naive_catches: list[dict],
    too_clean: list[str],
) -> tuple[str, str]:
    """Aggregate verdict + 1-line rationale."""
    # Any critical convergent (≥2 reviewers) → mandatory rework
    critical_convergent = [
        c for c in convergent
        if c["max_severity"] == "critical" and len(c["found_by"]) >= 2
    ]
    if critical_convergent:
        return "rework_required", (
            f"{len(critical_convergent)} critical issue(s) confirmed by ≥2 reviewers"
        )

    # Cross-family disagreement → mandatory director review
    cross_family_dis = [d for d in disagreements if d["kind"] == "cross-family"]
    if cross_family_dis:
        return "director_review_required", (
            f"{len(cross_family_dis)} cross-family disagreement(s) — framing contamination signal"
        )

    # Naive catches that weren't seen by stronger reviewers → director review
    if naive_catches:
        return "director_review_required", (
            f"{len(naive_catches)} obvious-miss finding(s) only naive reviewers flagged"
        )

    # Any rework_required verdict → director_review_required
    if any(o["data"].get("verdict") == "rework_required" for o in outputs):
        return "rework_required", "at least one reviewer demanded rework"

    # All satisfied with no flags → satisfied (rare on L-tier, normal on M)
    if all(o["data"].get("verdict") == "satisfied" for o in outputs):
        return "satisfied", f"all {len(outputs)} reviewer(s) satisfied"

    # Some too_clean → director review
    if too_clean:
        return "director_review_required", (
            f"{len(too_clean)} reviewer(s) flagged suspicious_too_clean"
        )

    return "director_review_required", "mixed signals — director must adjudicate"


def write_summary(
    eng: Path,
    iter_n: int,
    outputs: list[dict],
    clusters: list[dict],
    disagreements: list[dict],
    naive_catches: list[dict],
    too_clean: list[str],
    aggregate_verdict: str,
    rationale: str,
    similarity_pairs: list[dict] | None = None,
) -> Path:
    out = eng / "consilium-summary.md"
    lines: list[str] = []
    lines.append(f"# Consilium synthesis — iter {iter_n}")
    lines.append("")
    lines.append(f"**Aggregate verdict:** {aggregate_verdict}  ")
    lines.append(f"**Rationale:** {rationale}")
    lines.append("")

    lines.append("## Reviewer roster")
    lines.append("")
    lines.append("| Reviewer | Tier | Verdict | Findings | Summary |")
    lines.append("|---|---|---|---|---|")
    for o in outputs:
        role = o["role"]
        d = o["data"]
        v = d.get("verdict", "?")
        fc = len(d.get("findings", []))
        s = d.get("summary", "").replace("|", "\\|")[:80]
        lines.append(f"| {role} | {REVIEWER_TIERS.get(role, '?')} | {v} | {fc} | {s} |")
    lines.append("")

    if clusters:
        lines.append(f"## Findings ({len(clusters)} unique after dedup)")
        lines.append("")
        for i, c in enumerate(clusters, 1):
            roles_s = ", ".join(c["found_by"])
            lines.append(f"### {i}. **{c['max_severity'].upper()}** — {c['issue']}")
            lines.append(f"- Found by: {roles_s} ({len(c['found_by'])} reviewer(s))")
            if c.get("evidence_path"):
                lines.append(f"- Evidence: `{c['evidence_path']}`")
            if c.get("fix_hint"):
                lines.append(f"- Fix hint: {c['fix_hint']}")
            if len(c["all_descriptions"]) > 1:
                lines.append("- Variant descriptions:")
                for d in c["all_descriptions"][:3]:
                    lines.append(f"  - {d}")
            lines.append("")

    if disagreements:
        lines.append("## Disagreements")
        lines.append("")
        for d in disagreements:
            mark = "**[CROSS-FAMILY]**" if d["kind"] == "cross-family" else "[intra-family]"
            lines.append(
                f"- {mark} {d['reviewer_a']}={d['verdict_a']} vs "
                f"{d['reviewer_b']}={d['verdict_b']}"
            )
        if any(d["kind"] == "cross-family" for d in disagreements):
            lines.append("")
            lines.append("> Cross-family disagreement is a framing-contamination signal. "
                         "Director must adjudicate by inspecting the disputed finding directly.")
        lines.append("")

    if naive_catches:
        lines.append("## Naive-layer catches (obvious-miss signal)")
        lines.append("")
        lines.append("These findings were flagged ONLY by Sonnet/Haiku scoped reviewers. "
                     "Stronger reviewers may have rationalized past them.")
        lines.append("")
        for c in naive_catches:
            lines.append(f"- **{c['max_severity'].upper()}**: {c['issue']}")
            if c.get("evidence_path"):
                lines.append(f"  - Evidence: `{c['evidence_path']}`")
        lines.append("")

    if too_clean:
        lines.append("## Suspicious-too-clean flags")
        lines.append("")
        lines.append(f"Reviewer(s) returned 0 findings: {', '.join(too_clean)}. "
                     "Either work is genuinely clean OR reviewer scan was shallow.")
        lines.append("")

    if similarity_pairs:
        lines.append("## Similarity matrix (transparency)")
        lines.append("")
        lines.append("Pairwise similarity for findings the synth did NOT merge. "
                     "Director: if two findings are actually the same issue, mark in verdict; "
                     "if two findings sharing a path are actually distinct, also mark.")
        lines.append("")
        lines.append("| A | B | Issue similarity | Same evidence path |")
        lines.append("|---|---|---|---|")
        for p in similarity_pairs[:25]:  # cap to avoid bloat
            lines.append(
                f"| `{p['a_id']}` | `{p['b_id']}` | {p['issue_similarity']} | "
                f"{'✓' if p['same_evidence_path'] else '—'} |"
            )
        if len(similarity_pairs) > 25:
            lines.append(f"| ... | ({len(similarity_pairs) - 25} more pairs omitted) | | |")
        lines.append("")

    lines.append("## Statistics")
    lines.append("")
    lines.append(f"- Total raw findings: {sum(len(o['data'].get('findings', [])) for o in outputs)}")
    lines.append(f"- Unique after dedup: {len(clusters)}")
    convergent_count = sum(1 for c in clusters if len(c["found_by"]) >= 3)
    lines.append(f"- Convergent (≥3 reviewers agree): {convergent_count}")
    if outputs:
        agree_pairs = 0
        total_pairs = 0
        verdicts = [o["data"].get("verdict", "") for o in outputs]
        for i, va in enumerate(verdicts):
            for vb in verdicts[i + 1:]:
                total_pairs += 1
                if va == vb:
                    agree_pairs += 1
        if total_pairs:
            lines.append(f"- Pairwise verdict agreement: {agree_pairs}/{total_pairs} "
                         f"({100 * agree_pairs // total_pairs}%)")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*This synthesis is mechanical aggregation. Director writes the final "
                 "verdict in `acceptance-log.md`, citing this synthesis where appropriate.*")
    lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Consilium synthesizer for adversary outputs")
    parser.add_argument("engagement", help="Path to engagement/ directory")
    parser.add_argument("--iter", type=int, default=None,
                        help="Iteration number (default: read from engagement/iteration)")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON summary to stdout")
    args = parser.parse_args()

    eng = Path(args.engagement).resolve()
    if not eng.exists() or not eng.is_dir():
        print(f"ERROR: engagement directory not found: {eng}", file=sys.stderr)
        return 2

    iter_n = args.iter if args.iter is not None else read_iter_counter(eng)
    outputs = load_outputs(eng, iter_n)
    if not outputs:
        print(f"No adversary outputs found in {eng}/validation-outputs/ for iter={iter_n}",
              file=sys.stderr)
        print("Run `python ~/.claude/scripts/adversary_lg.py engagement/ --consilium {M|L}` first.",
              file=sys.stderr)
        return 1

    clusters = cluster_findings(outputs)
    disagreements = detect_disagreements(outputs)
    naive_catches = detect_naive_only_catches(clusters)
    too_clean = detect_suspicious_too_clean(outputs)
    similarity_pairs = compute_similarity_matrix(outputs)
    verdict, rationale = determine_aggregate_verdict(
        outputs, clusters, disagreements, naive_catches, too_clean,
    )

    summary_path = write_summary(
        eng, iter_n, outputs, clusters, disagreements, naive_catches, too_clean,
        verdict, rationale, similarity_pairs=similarity_pairs,
    )

    if args.json:
        print(json.dumps({
            "engagement": str(eng),
            "iter": iter_n,
            "reviewers": len(outputs),
            "unique_findings": len(clusters),
            "convergent_critical": sum(
                1 for c in clusters
                if c["max_severity"] == "critical" and len(c["found_by"]) >= 2
            ),
            "cross_family_disagreements": sum(1 for d in disagreements if d["kind"] == "cross-family"),
            "naive_only_catches": len(naive_catches),
            "too_clean_flags": too_clean,
            "aggregate_verdict": verdict,
            "rationale": rationale,
            "summary_path": str(summary_path),
        }, ensure_ascii=False, indent=2))
    else:
        print(f"Consilium synthesis (iter={iter_n}, {len(outputs)} reviewers)")
        print(f"  Aggregate verdict: {verdict}")
        print(f"  Rationale: {rationale}")
        print(f"  Unique findings: {len(clusters)}")
        if disagreements:
            cf = sum(1 for d in disagreements if d["kind"] == "cross-family")
            print(f"  Disagreements: {len(disagreements)} ({cf} cross-family)")
        if naive_catches:
            print(f"  Naive-only catches: {len(naive_catches)}")
        if too_clean:
            print(f"  Too-clean flags: {', '.join(too_clean)}")
        print(f"  Summary written: {summary_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
