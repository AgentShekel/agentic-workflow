#!/usr/bin/env python3
"""Agency metrics — one number per question the system currently cannot answer.

Motivation (2026-08-20 system-improvement session): the corpus measures its own
ACTIVITY in detail (32 skill-evolution signals, 14 archived engagements, a
90 KB orchestration engine) and its RESULT not at all. Concretely, before this
script existed:

  - override rate was recoverable only by hand-reading acceptance-log prose,
    and the canonical `### Verdict:` line was present in 6 of 14 engagements;
  - no ledger ever carried a `verdict_written` / `human_directive_received` /
    `validator_*` event, so the acceptance seam was invisible in the one place
    built to record it;
  - `optional/token-budget.py` reads a `metrics.jsonl` that exists nowhere.

Design rules, learned from the failure mode this replaces:

1. NEVER INVENT A NUMBER. A metric with no data source reports `no data` and
   says which event or artefact would supply it. A confident zero is worse than
   an honest gap, because it silently becomes a baseline.
2. EVERY METRIC HAS A THRESHOLD TRIPLE (baseline / target / alert) in
   `metrics-thresholds.json`. A metric without a target is decoration, so this
   script refuses to print one.
3. THE TEMPO RATIO IS IN TOKENS, with time as a fallback. Both sides must share
   a unit, and the engine cannot read a clock (Date.now is banned in that
   dialect), so only the engine's cumulative token snapshots can measure the
   delivery side. `validator_lg.py` supplies `elapsed_s` on the validation side
   and is used when no token snapshots exist. Snapshots are CUMULATIVE: a phase
   costs the delta since the previous one, and an engagement's total is the
   PEAK, never the sum (summing cumulative values multiplies the same tokens by
   the number of emit points).

Usage:
    python ~/.claude/scripts/metrics.py                 # full report
    python ~/.claude/scripts/metrics.py --json          # machine-readable
    python ~/.claude/scripts/metrics.py --hook          # SessionStart: quiet
    python ~/.claude/scripts/metrics.py --roots C:/work-projects C:/game-projects

--hook prints nothing unless a metric is in ALERT or the weekly cadence is due
(stamp file `~/.claude/.metrics-last-report`), so it cannot become noise that
gets trained away.
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
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Own dir first, canonical scripts dir second: a throwaway copy run from a temp
# dir during a red/green gate still needs to import lib.ledger.
sys.path.insert(0, str(Path(__file__).resolve().parent))
_CANON = Path.home() / ".claude" / "scripts"
if str(_CANON) not in sys.path:
    sys.path.append(str(_CANON))

DEFAULT_ROOTS = ["C:/work-projects", "C:/game-projects"]


def _thresholds_path() -> Path:
    """Sibling file, then the canonical scripts dir.

    The fallback exists for the gate pattern: proving a fix red-then-green runs
    a throwaway COPY of this script from a temp dir, where the sibling config is
    absent. Without the fallback every gate run silently loses its thresholds
    and the whole suite reports 'no target'.
    """
    import os
    env = os.environ.get("METRICS_THRESHOLDS")
    if env:
        return Path(env)
    sibling = Path(__file__).resolve().parent / "metrics-thresholds.json"
    if sibling.exists():
        return sibling
    return Path.home() / ".claude" / "scripts" / "metrics-thresholds.json"


THRESHOLDS_FILE = _thresholds_path()
STAMP_FILE = Path.home() / ".claude" / ".metrics-last-report"
REPORT_EVERY_DAYS = 7

# Verdict line the acceptance-protocol prescribes. Anything else is prose and
# is counted as MISSING rather than guessed at — see design rule 1.
VERDICT_RE = re.compile(r"^#{1,4}\s*Verdict:\s*(ACCEPT|REJECT|DIRECTED)\b", re.M | re.I)
# Adjudication markers the manager must place per consilium signal.
SUSTAINED_RE = re.compile(r"\b(SUSTAINED|REAL)\b")
OVERRULED_RE = re.compile(r"\b(OVERRULED|FALSE_POSITIVE)\b")


# ----------------------------------------------------------------- discovery

def find_engagements(roots: list[str]) -> list[Path]:
    """Every engagement dir: live `*/engagement` + `*/engagement-archived/*`."""
    out: list[Path] = []
    for root in roots:
        r = Path(root)
        if not r.is_dir():
            continue
        for project in sorted(p for p in r.iterdir() if p.is_dir()):
            live = project / "engagement"
            if live.is_dir():
                out.append(live)
            arch = project / "engagement-archived"
            if arch.is_dir():
                out += [d for d in sorted(arch.iterdir()) if d.is_dir()]
    return out


def _artefact(eng: Path, name: str) -> Path | None:
    """Engagement artefacts live either at the root or one level down
    (`primary/` for multi-track engagements). Both count."""
    direct = eng / name
    if direct.exists():
        return direct
    for sub in sorted(p for p in eng.iterdir() if p.is_dir()):
        cand = sub / name
        if cand.exists():
            return cand
    return None


def _read(p: Path | None) -> str:
    if p is None:
        return ""
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def collect(eng: Path) -> dict:
    """One engagement -> the raw facts every metric is derived from."""
    from lib.ledger import EventLedger

    # The ledger lives beside the other artefacts, which for a multi-track engagement means
    # `primary/`, not the engagement root. Reading only the root silently dropped every nested
    # engagement's events — caught when archiving an engagement moved its ledger under
    # primary/ and the corpus quietly lost 12 events and a whole rework series.
    ledger_file = _artefact(eng, "events.jsonl")
    ledger_dir = ledger_file.parent if ledger_file else eng
    events = EventLedger.read(ledger_dir)
    chain = EventLedger.verify_chain(ledger_dir)
    accept_log = _artefact(eng, "acceptance-log.md")
    criteria = _artefact(eng, "criteria.md")
    handoff = _artefact(eng, "handoff.md")
    directive = _artefact(eng, "human-directive.md")

    accept_body = _read(accept_log)
    verdicts = VERDICT_RE.findall(accept_body)
    crit_body = _read(criteria)
    tier = None
    m = re.search(r"^size:\s*([SML])\b", crit_body, re.M)
    if m:
        tier = m.group(1).upper()
    rm = re.search(r"^risk:\s*(low|medium|high)\b", crit_body, re.M | re.I)
    risk = rm.group(1).lower() if rm else None
    has_hypothesis = bool(re.search(r"^##\s*Outcome hypothesis", crit_body, re.M | re.I))

    types: dict[str, int] = {}
    for e in events:
        t = e.get("payload_type") or "?"
        types[t] = types.get(t, 0) + 1

    def elapsed_of(pred) -> float:
        total = 0.0
        for e in events:
            if pred(e):
                v = (e.get("payload") or {}).get("elapsed_s")
                if isinstance(v, (int, float)):
                    total += float(v)
        return total

    # Token snapshots are CUMULATIVE output tokens at each phase boundary, so the cost of a phase
    # is the delta since the previous snapshot. This is the only unit the production and the
    # validation side share: the engine cannot read a clock (Date.now is banned in that dialect),
    # so a time-based implementation-vs-validation ratio is not obtainable from the engine path.
    produce_tok = validate_tok = 0
    peak_tok = 0
    prev = 0
    for e in sorted(events, key=lambda x: x.get("timestamp") or ""):
        total_tok = (e.get("tokens") or {}).get("total")
        if not isinstance(total_tok, (int, float)):
            continue
        delta = max(0, int(total_tok) - prev)   # max(): a restarted run resets the counter
        prev = max(prev, int(total_tok))
        peak_tok = max(peak_tok, int(total_tok))
        t = e.get("payload_type")
        if t in ("wave_completed", "specialist_completed"):
            produce_tok += delta
        elif t in ("validator_completed", "budget_checkpoint") or str(t).startswith("consilium"):
            validate_tok += delta

    return {
        "path": str(eng),
        "name": eng.name if eng.name != "engagement" else f"{eng.parent.name}/engagement",
        "tier": tier,
        "risk": risk,
        "has_hypothesis": has_hypothesis,
        "events": len(events),
        "types": types,
        "chain_status": chain["status"],
        "has_ledger": bool(events),
        "has_handoff": handoff is not None,
        "has_acceptance_log": accept_log is not None,
        "has_directive": directive is not None,
        "verdict": verdicts[0].upper() if verdicts else None,
        "gate_decisions": [(e.get("payload") or {}).get("decision")
                           for e in events if e.get("payload_type") == "gate_decision"],
        "sustained": len(SUSTAINED_RE.findall(accept_body)),
        "overruled": len(OVERRULED_RE.findall(accept_body)),
        "post_accept_defects": types.get("post_accept_defect", 0),
        "outcome_checks": [(e.get("payload") or {}).get("result")
                           for e in events if e.get("payload_type") == "outcome_check"],
        # Cumulative snapshots: the engagement total is the PEAK, not the sum of snapshots
        # (summing cumulative values multiplies the same tokens by the number of emit points).
        "tokens_total": peak_tok,
        "produce_tokens": produce_tok,
        "validate_tokens": validate_tok,
        "produce_s": elapsed_of(lambda e: e.get("payload_type") in
                               ("specialist_completed", "wave_completed")),
        "validate_s": elapsed_of(lambda e: str(e.get("payload_type", "")).startswith("validator_")),
        "rework_reports": sum(
            1 for e in events
            if e.get("payload_type") == "specialist_completed"
            and "rework" in str((e.get("payload") or {}).get("report", "")).lower()),
        "specialist_reports": types.get("specialist_completed", 0),
    }


# ------------------------------------------------------------------- metrics

def _pct(num: int, den: int) -> float | None:
    return None if not den else round(100.0 * num / den, 1)


def compute(rows: list[dict]) -> dict:
    """rows -> {metric_key: {"value", "unit", "n", "note"}}. `value=None` means
    no data, and `note` must then name what would produce it."""
    total = len(rows)
    with_verdict = [r for r in rows if r["verdict"]]
    gate_calls = [d for r in rows for d in r["gate_decisions"] if d]

    # Override rate — ledger first (countable), acceptance-log prose as fallback.
    if gate_calls:
        overrides = sum(1 for d in gate_calls if d in ("DIRECTED", "REJECT"))
        override = {"value": _pct(overrides, len(gate_calls)), "unit": "%",
                    "n": len(gate_calls), "note": "from gate_decision events"}
    elif with_verdict:
        overrides = sum(1 for r in with_verdict if r["verdict"] in ("REJECT", "DIRECTED"))
        override = {"value": _pct(overrides, len(with_verdict)), "unit": "%",
                    "n": len(with_verdict),
                    "note": f"fallback: canonical verdict line, present in "
                            f"{len(with_verdict)}/{total} engagements. Emit "
                            f"gate_decision to make this countable."}
    else:
        override = {"value": None, "unit": "%", "n": 0,
                    "note": "no gate_decision events and no canonical verdict lines"}

    sustained = sum(r["sustained"] for r in rows)
    overruled = sum(r["overruled"] for r in rows)
    agreement = ({"value": _pct(sustained, sustained + overruled), "unit": "%",
                  "n": sustained + overruled,
                  "note": "adjudication markers in acceptance-log"}
                 if sustained + overruled else
                 {"value": None, "unit": "%", "n": 0,
                  "note": "no SUSTAINED/OVERRULED markers found"})

    produce_tok = sum(r["produce_tokens"] for r in rows)
    validate_tok = sum(r["validate_tokens"] for r in rows)
    produce = sum(r["produce_s"] for r in rows)
    validate = sum(r["validate_s"] for r in rows)
    if produce_tok > 0 and validate_tok > 0:
        # Preferred: both sides in tokens, from the engine's cumulative snapshots.
        tempo = {"value": round(produce_tok / validate_tok, 2), "unit": "x", "n": len(rows),
                 "note": f"token cost of delivery ({produce_tok:,}) vs validation ({validate_tok:,})"}
    elif validate > 0 and produce > 0:
        tempo = {"value": round(produce / validate, 2), "unit": "x", "n": len(rows),
                 "note": "elapsed_s of specialist+wave vs validator events"}
    elif validate > 0:
        # The false zero again, wearing a different hat: validator events carry elapsed_s,
        # specialist/wave events do not, so the ratio computes to 0.0 and reads as "validation
        # is infinitely ahead of production" when it means the production side is unmeasured.
        tempo = {"value": None, "unit": "x", "n": len(rows),
                 "note": f"validator elapsed_s totals {validate:.0f}s but the production side "
                         f"reports none — a ratio needs BOTH sides timed. specialist_completed / "
                         f"wave_completed must carry elapsed_s (the engine's A.ledger emit is the "
                         f"place to add it)"}
    else:
        tempo = {"value": None, "unit": "x", "n": 0,
                 "note": "no validator_* events with elapsed_s. validator_lg.py DOES emit "
                         "them; the engine's validate phase is agent-driven and never routes "
                         "through it, so the engine path produces none — A.ledger closes that"}

    reports = sum(r["specialist_reports"] for r in rows)
    rework = sum(r["rework_reports"] for r in rows)
    rework_rate = ({"value": _pct(rework, reports), "unit": "%", "n": reports,
                    "note": "specialist reports whose filename marks a rework"}
                   if reports else
                   {"value": None, "unit": "%", "n": 0, "note": "no specialist_completed events"})

    complete = sum(1 for r in rows
                   if r["has_handoff"] and r["has_acceptance_log"] and r["has_ledger"])
    evidence = {"value": _pct(complete, total), "unit": "%", "n": total,
                "note": "engagements with handoff + acceptance-log + a ledger"}

    ledgered = sum(1 for r in rows if r["has_ledger"])
    coverage = {"value": _pct(ledgered, total), "unit": "%", "n": total,
                "note": "engagements that produced any ledger at all"}

    canonical = {"value": _pct(len(with_verdict), total), "unit": "%", "n": total,
                 "note": "acceptance-log carries the canonical `### Verdict:` line"}

    l_share = sum(1 for r in rows if r["tier"] == "L")
    tiering = {"value": _pct(l_share, sum(1 for r in rows if r["tier"])), "unit": "%",
               "n": sum(1 for r in rows if r["tier"]),
               "note": "share of engagements run at L tier"}

    defects = sum(r["post_accept_defects"] for r in rows)
    accepted = sum(1 for r in rows if r["verdict"] == "ACCEPT")
    if not accepted:
        cfr = {"value": None, "unit": "%", "n": 0, "note": "no accepted engagements"}
    elif not defects:
        # Design rule 1, the sharpest case: zero defects and zero defect events
        # are indistinguishable from here, and a confident 0% would quietly
        # become the baseline for "quality is fine".
        cfr = {"value": None, "unit": "%", "n": accepted,
               "note": f"{accepted} accepted engagements and zero post_accept_defect "
                       f"events — that is an empty feed, not a clean record. Emit the "
                       f"event when a shipped engagement needs a fix."}
    else:
        cfr = {"value": _pct(defects, accepted), "unit": "%", "n": accepted,
               "note": "post_accept_defect events per accepted engagement"}

    outcomes = [o for r in rows for o in r["outcome_checks"] if o]
    ovr = ({"value": _pct(sum(1 for o in outcomes if o == "confirmed"), len(outcomes)),
            "unit": "%", "n": len(outcomes), "note": "outcome_check events"}
           if outcomes else
           {"value": None, "unit": "%", "n": 0,
            "note": "no outcome_check events — criteria.md carries no outcome "
                    "hypothesis to close"})

    tokens = sum(r["tokens_total"] for r in rows)   # peak per engagement, summed across them
    cost = ({"value": tokens, "unit": "tok", "n": len(rows), "note": "aggregate token fields (v2)"}
            if tokens else
            {"value": None, "unit": "tok", "n": 0,
             "note": "no event carries a `tokens` aggregate — token-budget.py has "
                     "no data source"})

    high = [r for r in rows if r["risk"] == "high"]
    if not high:
        ungated = {"value": None, "unit": "%", "n": 0,
                   "note": "no engagement declares `risk: high` yet — the axis was added "
                           "2026-08-20 and is unset on everything before it"}
    else:
        skipped = sum(1 for r in high if not r["gate_decisions"])
        ungated = {"value": _pct(skipped, len(high)), "unit": "%", "n": len(high),
                   "note": "high-risk engagements with no gate_decision event — the "
                           "irreversible work that took the cheap path"}

    hypo = {"value": _pct(sum(1 for r in rows if r["has_hypothesis"]), total),
            "unit": "%", "n": total,
            "note": "criteria.md carrying an `## Outcome hypothesis` section"}

    return {
        "override_rate": override,
        "high_risk_ungated_rate": ungated,
        "outcome_hypothesis_rate": hypo,
        "agreement_rate": agreement,
        "iv_tempo_ratio": tempo,
        "rework_rate": rework_rate,
        "evidence_completeness": evidence,
        "ledger_coverage": coverage,
        "verdict_canonical_rate": canonical,
        "l_tier_share": tiering,
        "post_accept_defect_rate": cfr,
        "outcome_validation_rate": ovr,
        "tokens_recorded": cost,
    }


# ------------------------------------------------------------------ verdicts

def load_thresholds() -> dict:
    try:
        return json.loads(THRESHOLDS_FILE.read_text(encoding="utf-8"))["metrics"]
    except Exception as e:  # noqa: BLE001 — a broken config must not hide the data
        print(f"WARNING [metrics]: cannot read {THRESHOLDS_FILE.name} ({e}); "
              f"reporting values without status", file=sys.stderr)
        return {}


def status_of(key: str, value, th: dict) -> str:
    """OK / WARN / ALERT / no target. `direction` says which way is bad."""
    spec = th.get(key)
    if not spec:
        return "no target"
    if value is None:
        return "no data"
    target, alert = spec.get("target"), spec.get("alert")
    direction = spec.get("direction", "higher_is_better")
    if direction == "band":
        lo, hi = spec["band"]
        if lo <= value <= hi:
            return "OK"
        return "ALERT" if (value < lo * 0.5 or value > hi * 1.5) else "WARN"
    if direction == "lower_is_better":
        if alert is not None and value >= alert:
            return "ALERT"
        return "OK" if target is None or value <= target else "WARN"
    if alert is not None and value <= alert:
        return "ALERT"
    return "OK" if target is None or value >= target else "WARN"


def render(rows: list[dict], metrics: dict, th: dict) -> str:
    lines = [f"Agency metrics — {len(rows)} engagements "
             f"({sum(1 for r in rows if r['has_ledger'])} with a ledger, "
             f"{sum(r['events'] for r in rows)} events)", ""]
    width = max(len(k) for k in metrics)
    for key, m in metrics.items():
        spec = th.get(key, {})
        st = status_of(key, m["value"], th)
        val = "no data" if m["value"] is None else f"{m['value']}{m['unit']}"
        tgt = ""
        if spec:
            if spec.get("direction") == "band":
                tgt = f"target {spec['band'][0]}-{spec['band'][1]}{m['unit']}"
            elif spec.get("target") is not None:
                tgt = f"target {spec['target']}{m['unit']}"
        lines.append(f"  {key:<{width}}  {val:>10}  {st:<8} {tgt:<16} n={m['n']}")
        if m["value"] is None or st in ("WARN", "ALERT"):
            lines.append(f"  {'':<{width}}  -> {m['note']}")
    bad_chain = [r for r in rows if r["chain_status"] == "tamper"]
    if bad_chain:
        lines += ["", "CHAIN TAMPER: " + ", ".join(r["name"] for r in bad_chain)]
    return "\n".join(lines)


# --------------------------------------------------------------------- entry

def _read_stamp() -> tuple[datetime | None, list[str]]:
    """(last report time, alert set reported then). Tolerates the v1 stamp,
    which was a bare ISO timestamp."""
    try:
        raw = STAMP_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return None, []
    try:
        data = json.loads(raw)
        return datetime.fromisoformat(data["ts"]), sorted(data.get("alerts", []))
    except Exception:  # noqa: BLE001 — v1 stamp or corrupt: treat as no alert memory
        try:
            return datetime.fromisoformat(raw), []
        except ValueError:
            return None, []


def _should_speak(alerts: list[str]) -> bool:
    """Speak on NEW information, then shut up.

    A hook that repeats the same three ALERTs at every session start is
    wallpaper within a day, and the metric it guards dies with it. So: report
    when the alert SET changes (something broke, or something got fixed), or
    when the weekly cadence comes due. A standing, already-seen alert is not
    news — it stays in the full report, where it is asked for deliberately.
    """
    last_ts, last_alerts = _read_stamp()
    if last_ts is None:
        return True
    if sorted(alerts) != last_alerts:
        return True
    return datetime.now(timezone.utc) - last_ts >= timedelta(days=REPORT_EVERY_DAYS)


def _stamp(alerts: list[str] | None = None) -> None:
    try:
        STAMP_FILE.write_text(json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(),
            "alerts": sorted(alerts or []),
        }), encoding="utf-8")
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Compute agency metrics from engagement ledgers.")
    ap.add_argument("--roots", nargs="*", default=DEFAULT_ROOTS)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--hook", action="store_true",
                    help="SessionStart mode: silent unless ALERT or weekly cadence due")
    args = ap.parse_args(argv)

    engagements = find_engagements(args.roots)
    if not engagements:
        if not args.hook:
            print(f"no engagements found under {', '.join(args.roots)}")
        return 0

    rows = [collect(e) for e in engagements]
    metrics = compute(rows)
    th = load_thresholds()

    if args.json:
        print(json.dumps({"engagements": rows, "metrics": metrics}, ensure_ascii=False, indent=2))
        return 0

    alerts = [k for k, m in metrics.items() if status_of(k, m["value"], th) == "ALERT"]
    if args.hook:
        if not _should_speak(alerts):
            return 0
        _, previously = _read_stamp()
        head = (f"metrics: {len(rows)} engagements | "
                + " | ".join(f"{k}={metrics[k]['value']}{metrics[k]['unit']}"
                             for k in ("override_rate", "ledger_coverage", "evidence_completeness")
                             if metrics[k]["value"] is not None))
        print(head)
        if alerts:
            fresh = [a for a in alerts if a not in previously]
            cleared = [a for a in previously if a not in alerts]
            print("  ALERT: " + ", ".join(alerts)
                  + (f"  (new: {', '.join(fresh)})" if fresh and previously else ""))
            if cleared:
                print("  cleared: " + ", ".join(cleared))
        elif previously:
            print("  all clear — cleared: " + ", ".join(previously))
        print("  full report: python ~/.claude/scripts/metrics.py")
        _stamp(alerts)
        return 0

    print(render(rows, metrics, th))
    _stamp(alerts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
