"""consilium-fidelity: the summary the human judges must say what the role finals say.

Field incident (2026-06-24): the consilium-summary.md in front of the human
gate was not written by consilium-synth.py. It said PROCEED over role finals that said
rework_required, and nothing compared the two. synth cannot produce that on its own
(rework_required dominates its aggregate), so the check recomputes the aggregate with
synth's own functions and compares; it also dates the finals against the last code
commit, because a consilium on an older tree reviews something that is no longer there.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

_SYNTH = Path(__file__).resolve().parents[2] / "consilium-synth.py"
_AGG_RE = re.compile(r"^\*\*Aggregate verdict:\*\*\s*([A-Za-z_]+)", re.MULTILINE)
_ITER_RE = re.compile(r"^#\s*Consilium synthesis\s*\W+\s*iter\s+(\d+)", re.MULTILINE | re.IGNORECASE)
_FINAL_RE = re.compile(r"^(?P<role>[\w-]+?)-iter-(?P<iter>\d+)-(?P<ts>[\d\w]+)\.json$")
_SLACK_S = 120  # clock skew between a stamp and a commit time


def _load_synth():
    spec = importlib.util.spec_from_file_location("_consilium_synth_for_precheck", _SYNTH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _size(eng: Path) -> str | None:
    crit = eng / "criteria.md"
    if not crit.is_file():
        return None
    m = re.search(r"^size:\s*([SML])\b", crit.read_text(encoding="utf-8", errors="replace"), re.MULTILINE)
    return m.group(1) if m else None


def _final_times(eng: Path, iter_n: int, roles) -> list[float]:
    """Epoch seconds of the latest final per role (Z stamps parsed, otherwise mtime)."""
    latest: dict[str, tuple[str, Path]] = {}
    for f in (eng / "validation-outputs").glob("*.json"):
        m = _FINAL_RE.match(f.name)
        if not m or int(m.group("iter")) != iter_n or m.group("role") not in roles:
            continue
        try:  # same selection as synth's load_outputs: an unparseable final is not the review
            json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if m.group("role") not in latest or m.group("ts") > latest[m.group("role")][0]:
            latest[m.group("role")] = (m.group("ts"), f)
    out = []
    for ts, f in latest.values():
        digits = re.sub(r"\D", "", ts)
        if ts.endswith("Z") and len(digits) >= 14:
            out.append(datetime.strptime(digits[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc).timestamp())
        else:
            out.append(f.stat().st_mtime)
    return out


def _last_code_commit(eng: Path) -> float | None:
    """Commit time of the newest commit touching the repo outside the engagement dir."""
    try:
        top = subprocess.run(["git", "-C", str(eng), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=20, check=False)
        if top.returncode != 0:
            return None
        root = Path(top.stdout.strip()).resolve()
        rel = eng.resolve().relative_to(root).as_posix()
        log = subprocess.run(["git", "-C", str(root), "log", "-1", "--format=%ct", "--", ".", f":(exclude){rel}"],
                             capture_output=True, text=True, timeout=20, check=False)
        return float(log.stdout.strip()) if log.returncode == 0 and log.stdout.strip() else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def check_consilium_fidelity(eng: Path) -> dict:
    name = "consilium-fidelity"
    summary = eng / "consilium-summary.md"
    if not summary.is_file():
        return {"name": name, "status": "skip", "detail": "no consilium-summary.md yet"}
    text = summary.read_text(encoding="utf-8", errors="replace")
    regen = "Regenerate it: python ~/.claude/scripts/consilium-synth.py engagement/ --tier {M|L}."
    agg = _AGG_RE.search(text)
    if not agg:
        return {"name": name, "status": "fail",
                "detail": "consilium-summary.md has no `**Aggregate verdict:**` line, so it was not written by "
                          "consilium-synth.py and nothing ties it to the role finals.",
                "fix": regen + " Notes for the human go in human-directive.md, not in the summary."}
    claimed = agg.group(1)

    synth = _load_synth()
    current = synth.read_iter_counter(eng)
    m_iter = _ITER_RE.search(text)
    iter_n = int(m_iter.group(1)) if m_iter else current
    if iter_n != current:
        if synth.load_outputs(eng, current):
            return {"name": name, "status": "fail",
                    "detail": f"consilium-summary.md describes iter {iter_n}, but iter-{current} role finals exist: "
                              "the human would judge the previous consilium.", "fix": regen}
        return {"name": name, "status": "skip",
                "detail": f"summary is from iter {iter_n}; the iter-{current} consilium has not run yet"}
    outputs = synth.load_outputs(eng, iter_n)
    if not outputs:
        return {"name": name, "status": "fail",
                "detail": f"consilium-summary.md speaks for iter {iter_n} but validation-outputs/ holds no role "
                          f"final for iter {iter_n}.", "fix": regen}
    clusters = synth.cluster_findings(outputs)
    base, _ = synth.determine_aggregate_verdict(
        outputs, clusters, synth.detect_disagreements(outputs),
        synth.detect_naive_only_catches(clusters), synth.detect_suspicious_too_clean(outputs))
    # The roster synth was run with (adversary_lg passes --tier) need not match criteria size:
    # an M engagement may get an L consilium. Rosters change only the failed-role accounting,
    # which can only make the aggregate stricter, so any roster's result is a genuine synth
    # output; a softened summary over rework_required finals matches none of them.
    size = _size(eng)
    rosters = [size if size in ("M", "L") else None, "M", "L", None]
    candidates = []
    for tier in rosters:
        _, failed = synth.find_failed_roles(eng, iter_n, outputs, tier)
        candidates.append(synth.account_for_failed_roles(base, "", failed)[0])
    verdict = candidates[0]
    if claimed not in candidates:
        per_role = ", ".join(f"{o['role']}={o['data'].get('verdict', '?')}" for o in outputs)
        return {"name": name, "status": "fail",
                "detail": f"consilium-summary.md says `{claimed}`, the iter-{iter_n} role finals aggregate to "
                          f"`{verdict}` ({per_role}).", "fix": regen}

    times = _final_times(eng, iter_n, {o["role"] for o in outputs})
    commit = _last_code_commit(eng)
    if times and commit is not None and commit > min(times) + _SLACK_S:
        stamp = datetime.fromtimestamp(commit, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        oldest = datetime.fromtimestamp(min(times), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return {"name": name, "status": "fail",
                "detail": f"code was committed at {stamp}, after the oldest iter-{iter_n} role final ({oldest}): "
                          "the consilium reviewed an older tree.",
                "fix": "Re-run the consilium on the current tree (adversary_lg.py --consilium {M|L}), then synth."}
    fresh = "finals not older than the last code commit" if commit is not None else "no git history to date against"
    return {"name": name, "status": "pass",
            "detail": f"summary `{claimed}` matches the iter-{iter_n} finals ({len(outputs)} role(s)); {fresh}"}
