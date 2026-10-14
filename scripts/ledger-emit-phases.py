#!/usr/bin/env python3
"""Emit the post-seam phase_completed events from the engagement-workflow return.

`engagement-workflow.js` writes no `events.jsonl` entries for the pre-gate cascade,
so agency-intake step 2a emits them afterwards. Until now that meant hand-typing
three `--payload-json` blobs while reading fields off a returned object. One
engagement is fine; a stream of them is repeated manual JSON, and the failure mode
is not a crash — it is a payload that looks right and carries a field nobody
returned. A fabricated ledger is worse than an empty one, because metrics.py and
skillopt-ready.py read it as fact.

This script derives every payload mechanically from the return object. A key that
is absent from the return is absent from the payload; nothing is defaulted, filled
in, or guessed.

Emits (only what the return actually supports):
  deliver   {"waveSummaries": r.waves}
  validate  {"adversarial_verify": r.adversarial_verify, "validation_files": r.validation_files}
  gate      {"failures": r.gate.failures, "readyForAcceptance": r.readyForAcceptance}

On a PRE-gate hard stop (an `error` and no `waves`), emits a single deliver event
carrying {"error", "failures", "readyForAcceptance": false} instead, matching the
contract agency-intake already documents.

Usage:
  python ~/.claude/scripts/ledger-emit-phases.py engagement/ --result result.json
  <workflow return> | python ~/.claude/scripts/ledger-emit-phases.py engagement/ --result -
  python ~/.claude/scripts/ledger-emit-phases.py engagement/ --result result.json --dry-run

Best-effort, like ledger-emit.py: observability must never break real work. Any
failure warns on stderr and exits 0. Only a malformed CLI invocation exits non-zero.
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

sys.path.insert(0, str(Path(__file__).resolve().parent))

MISSING = object()


def _warn(msg: str) -> None:
    print(f"WARNING [ledger-emit-phases]: {msg}", file=sys.stderr)


def _get(obj: dict, key: str):
    """Return obj[key] or MISSING. A present-but-null value counts as present:
    the workflow returning null is information, inventing a value is not."""
    return obj[key] if isinstance(obj, dict) and key in obj else MISSING


def build_events(result: dict) -> list[dict]:
    """Map a workflow return object to the events it actually supports.

    Pure and side-effect free so the mapping can be tested without a ledger.
    Returns a list of {"phase": str, "payload": dict}.
    """
    if not isinstance(result, dict):
        return []

    waves = _get(result, "waves")
    error = _get(result, "error")

    # PRE-gate hard stop: an error and no waves means no consolidation ran.
    if error is not MISSING and waves is MISSING:
        payload: dict = {"error": error, "readyForAcceptance": False}
        gate = result.get("gate")
        if isinstance(gate, dict) and "failures" in gate:
            payload["failures"] = gate["failures"]
        return [{"phase": "deliver", "payload": payload}]

    events: list[dict] = []

    if waves is not MISSING:
        events.append({"phase": "deliver", "payload": {"waveSummaries": waves}})

    validate_payload = {}
    for key in ("adversarial_verify", "validation_files"):
        value = _get(result, key)
        if value is not MISSING:
            validate_payload[key] = value
    if validate_payload:
        events.append({"phase": "validate", "payload": validate_payload})

    gate_payload = {}
    gate = result.get("gate")
    if isinstance(gate, dict) and "failures" in gate:
        gate_payload["failures"] = gate["failures"]
    ready = _get(result, "readyForAcceptance")
    if ready is not MISSING:
        gate_payload["readyForAcceptance"] = ready
    if gate_payload:
        events.append({"phase": "gate", "payload": gate_payload})

    return events


def _load_result(source: str) -> dict | None:
    try:
        raw = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    except OSError as e:
        _warn(f"cannot read result ({source}): {e}")
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        _warn(f"result is not valid JSON: {e}")
        return None
    if not isinstance(data, dict):
        _warn(f"result must be a JSON object, got {type(data).__name__}")
        return None
    return data


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Emit phase_completed events from an engagement-workflow return")
    parser.add_argument("engagement", help="Path to engagement/ directory")
    parser.add_argument("--result", required=True,
                        help="Path to the workflow return JSON, or '-' for stdin")
    parser.add_argument("--agent", default="agency-intake",
                        help="Actor recorded on the events (default: agency-intake)")
    parser.add_argument("--tier", choices=["S", "M", "L"],
                        help="Override tier; default reads result.tier when present")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the events that would be emitted, write nothing")
    parser.add_argument("--quiet", action="store_true", help="Suppress the per-event summary")
    args = parser.parse_args()

    result = _load_result(args.result)
    if result is None:
        return 0  # best-effort

    events = build_events(result)
    if not events:
        _warn("the return object carries none of waves / adversarial_verify / "
              "validation_files / gate.failures / readyForAcceptance — nothing to emit. "
              "Emitting a placeholder would be fabrication, so nothing was written.")
        return 0

    if args.dry_run:
        for ev in events:
            print(json.dumps(ev, ensure_ascii=False))
        return 0

    eng = Path(args.engagement).resolve()
    if not eng.exists():
        _warn(f"engagement directory not found: {eng} (events not recorded)")
        return 0

    tier = args.tier or (result.get("tier") if result.get("tier") in ("S", "M", "L") else None)

    try:
        from lib.ledger import EventLedger
    except Exception as e:
        _warn(f"lib.ledger unavailable ({e}); events not recorded")
        return 0

    try:
        ledger = EventLedger(eng, agent=args.agent, tier=tier)
    except Exception as e:
        _warn(f"ledger init failed ({e}); events not recorded")
        return 0

    written = 0
    for ev in events:
        try:
            ledger.emit("phase_completed",
                        node=f"phase:{ev['phase']}",
                        payload=ev["payload"])
            written += 1
        except Exception as e:
            _warn(f"emit failed for phase {ev['phase']}: {e}")

    if not args.quiet:
        print(f"ledger-emit-phases: {written}/{len(events)} event(s) written to "
              f"{eng / 'events.jsonl'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
