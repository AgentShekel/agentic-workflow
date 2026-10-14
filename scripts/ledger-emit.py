#!/usr/bin/env python3
"""Thin CLI shim over lib.ledger.EventLedger for markdown agents.

Leads and specialists are markdown agents invoked via `claude -p --agent X`;
they cannot `import lib.ledger` to emit events the way the Python orchestrators
(validator_lg / adversary_lg / handoff-precheck / engagement_lg) do. This CLI
gives them a one-line, best-effort emit path so the orchestration layer stops
being invisible in `engagement/events.jsonl`.

Closes skill-evolution signal #3 (2026-05-28 S field test): "lead/specialist
do NOT emit events to events.jsonl — only handoff-precheck + sub-engines."
Extended 2026-05-29 with the Authority rules 6/7 modes so markdown leads can
emit authority_conflict + skill snapshots (previously Python-API only).

Three modes (exactly one required):
  --type X             lifecycle event (phase_started, specialist_dispatched, ...)
  --snapshot-skills    Authority rule 7 — walk the skills dir, emit a skill
                       snapshot (engagement_started carrying name+hash per skill)
  --authority-conflict Authority rule 6 — emit authority_conflict (requires
                       --conflict-kind; omit --resolution for a BLOCKING conflict)

Design: BEST-EFFORT. Observability must never break real work. Any failure
(ledger module missing, engagement dir absent, unknown payload type, bad args,
emit exception) prints a WARNING to stderr and exits 0. Only a structurally
malformed CLI invocation (missing --agent) exits non-zero (argparse, exit 2).

Usage:
  python ~/.claude/scripts/ledger-emit.py ENGAGEMENT --agent dev-lead --tier M \
      --type phase_completed --phase plan --note "3 specialists planned"

  python ~/.claude/scripts/ledger-emit.py ENGAGEMENT --agent dev-backend-engineer \
      --type specialist_completed --report executor-reports/dev-backend-engineer.md

  # Rule 7 — skill snapshot at engagement start (richer engagement_started):
  python ~/.claude/scripts/ledger-emit.py ENGAGEMENT --agent dev-lead --tier M --snapshot-skills

  # Rule 6 — blocking authority conflict (no --resolution => verdict REJECT):
  python ~/.claude/scripts/ledger-emit.py ENGAGEMENT --agent dev-lead --tier M \
      --authority-conflict --conflict-kind skill_vs_agent_body \
      --sources-json '[{"kind":"skill","name":"engagement-protocol","claim":"heartbeat per phase"},
                       {"kind":"agent","name":"dev-lead","claim":"heartbeat per sub-task"}]'

Convenience flags build the lifecycle payload; --payload-json merges/overrides
for anything not covered. --node defaults to "phase:{phase}" when --phase given.
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

# Make `import lib.ledger` work regardless of CWD (script lives in scripts/).
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _warn(msg: str) -> None:
    print(f"WARNING [ledger-emit]: {msg} (event not recorded; continuing)",
          file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Emit one engagement event to events.jsonl "
                    "(best-effort; never blocks real work).",
    )
    parser.add_argument("engagement", help="Path to engagement/ directory")
    parser.add_argument("--agent",
                        help="Emitting agent name, e.g. dev-lead. Required for every "
                             "emit mode; not needed by --verify, which writes nothing.")

    # --- mode selectors (exactly one required) ---
    parser.add_argument("--type", dest="payload_type",
                        help="Lifecycle payload type (see KNOWN_PAYLOAD_TYPES in "
                             "lib/ledger.py). Mutually exclusive with the two mode flags.")
    parser.add_argument("--snapshot-skills", action="store_true",
                        help="Mode: walk the skills dir and emit a skill snapshot "
                             "(Authority rule 7). Lead runs once at engagement start.")
    parser.add_argument("--authority-conflict", action="store_true",
                        help="Mode: emit an authority_conflict event (Authority rule 6). "
                             "Requires --conflict-kind.")
    parser.add_argument("--verify", action="store_true",
                        help="Mode: verify the v2 hash chain instead of emitting. "
                             "Exits 1 on tamper (edited/removed past event); fork "
                             "(concurrent writers) and a legacy v1 prefix are exit 0.")

    # --- shared / lifecycle flags ---
    parser.add_argument("--tier", choices=["S", "M", "L"],
                        help="Engagement tier from criteria.md")
    parser.add_argument("--node",
                        help="Logical position, e.g. phase:plan (defaults to phase:{phase})")
    parser.add_argument("--phase",
                        help="Phase name; sets payload.phase and the default --node")
    parser.add_argument("--specialist",
                        help="Specialist agent name (for *_dispatched events)")
    parser.add_argument("--report",
                        help="Path to executor-report (for specialist_completed)")
    parser.add_argument("--note", help="Free-text note added to payload")
    parser.add_argument("--verdict", choices=["ACCEPT", "REJECT", "DIRECTED", "N/A"],
                        help="Optional verdict field")
    parser.add_argument("--payload-json",
                        help="JSON object merged into payload (overrides convenience flags)")
    parser.add_argument("--decision", choices=["PROCEED", "DIRECTED", "REJECT"],
                        help="(--type gate_decision) the human gate decision. Sets "
                             "payload.decision — required for that type, which is "
                             "what makes override rate countable.")
    parser.add_argument("--gate", help="(--type gate_decision) which gate: "
                                       "human-directive | manager-verdict")
    parser.add_argument("--tokens-json",
                        help="Aggregate cost for the work this event closes, e.g. "
                             "'{\"total\": 412000}'. AGGREGATES ONLY — no per-call traces.")

    # --- --snapshot-skills flags ---
    parser.add_argument("--skills-dir",
                        help="(--snapshot-skills) skills dir to walk; default ~/.claude/skills")

    # --- --authority-conflict flags ---
    parser.add_argument("--conflict-kind",
                        help="(--authority-conflict) e.g. skill_vs_agent_body, two_skills_overlap, "
                             "criteria_waives_protocol_gate, skill_version_drift_mid_engagement")
    parser.add_argument("--sources-json",
                        help="(--authority-conflict) JSON array of {kind,name,claim} objects")
    parser.add_argument("--resolution",
                        help="(--authority-conflict) outcome string; OMIT for a BLOCKING conflict "
                             "(verdict=REJECT, halt + escalate to judge)")
    parser.add_argument("--decided-by",
                        help="(--authority-conflict) auto-precedence | judge | <agent-name>")

    parser.add_argument("--quiet", action="store_true",
                        help="Suppress the emitted event_id line on success")
    args = parser.parse_args()

    # --- everything below is best-effort: soft-fail returns exit 0 ---
    mode_count = sum([bool(args.payload_type), args.snapshot_skills,
                      args.authority_conflict, args.verify])
    if mode_count != 1:
        _warn("specify exactly one of --type / --snapshot-skills / "
              "--authority-conflict / --verify")
        return 0
    if not args.verify and not args.agent:
        _warn("--agent is required for every emit mode")
        return 0

    try:
        from lib.ledger import EventLedger, KNOWN_PAYLOAD_TYPES
    except Exception as e:  # ledger module unavailable / stripped install
        _warn(f"cannot import lib.ledger ({e})")
        return 0

    eng = Path(args.engagement)
    if not eng.exists() or not eng.is_dir():
        _warn(f"engagement directory not found: {eng}")
        return 0

    # Mode: verify chain (a CHECK, not an emit — it may fail loudly) ---------
    if args.verify:
        rep = EventLedger.verify_chain(eng)
        head = (f"chain {rep['status']}: {rep['events']} events "
                f"({rep['chained']} chained, {rep['legacy_prefix']} legacy v1)")
        print(head)
        for p in rep["problems"][:20]:
            print(f"  {p['kind']:6} line {p['line']} {p.get('event_id') or ''}: {p['detail']}")
        return 1 if rep["status"] == "tamper" else 0

    try:
        led = EventLedger(eng, agent=args.agent, tier=args.tier)

        # Mode: skill snapshot (Authority rule 7) ---------------------------
        if args.snapshot_skills:
            skills_dir = Path(args.skills_dir) if args.skills_dir else (Path.home() / ".claude" / "skills")
            skills = EventLedger.snapshot_skills(skills_dir)
            event_id = led.emit_skill_snapshot(skills=skills)
            if not args.quiet:
                print(f"{event_id}  (skill snapshot: {len(skills)} skills from {skills_dir})")
            return 0

        # Mode: authority conflict (Authority rule 6) -----------------------
        if args.authority_conflict:
            if not args.conflict_kind:
                _warn("--authority-conflict requires --conflict-kind")
                return 0
            sources: list = []
            if args.sources_json:
                try:
                    parsed = json.loads(args.sources_json)
                    if isinstance(parsed, list):
                        sources = parsed
                    else:
                        _warn("--sources-json is not a JSON array; using []")
                except json.JSONDecodeError as e:
                    _warn(f"--sources-json invalid JSON ({e}); using []")
            event_id = led.emit_authority_conflict(
                conflict_kind=args.conflict_kind,
                sources=sources,
                resolution=args.resolution,   # None => blocking, verdict REJECT
                decided_by=args.decided_by,
            )
            if not args.quiet:
                tail = "  BLOCKING (resolution=None; halt + escalate)" if not args.resolution else ""
                print(f"{event_id}{tail}")
            return 0

        # Mode: lifecycle event (default --type) ----------------------------
        if args.payload_type not in KNOWN_PAYLOAD_TYPES:
            _warn(f"unknown --type {args.payload_type!r}; valid types: "
                  f"{', '.join(KNOWN_PAYLOAD_TYPES)}")
            return 0

        payload: dict = {}
        if args.decision:
            payload["decision"] = args.decision
        if args.gate:
            payload["gate"] = args.gate
        if args.phase:
            payload["phase"] = args.phase
        if args.specialist:
            payload["specialist"] = args.specialist
        if args.report:
            payload["report"] = args.report
        if args.note:
            payload["note"] = args.note
        if args.payload_json:
            try:
                extra = json.loads(args.payload_json)
                if isinstance(extra, dict):
                    payload.update(extra)
                else:
                    _warn("--payload-json is not a JSON object; ignored")
            except json.JSONDecodeError as e:
                _warn(f"--payload-json is invalid JSON ({e}); ignored")

        tokens = None
        if args.tokens_json:
            try:
                parsed = json.loads(args.tokens_json)
                if isinstance(parsed, dict):
                    tokens = parsed
                else:
                    _warn("--tokens-json is not a JSON object; ignored")
            except json.JSONDecodeError as e:
                _warn(f"--tokens-json is invalid JSON ({e}); ignored")

        node = args.node or (f"phase:{args.phase}" if args.phase else None)
        event_id = led.emit(
            args.payload_type,
            node=node,
            payload=payload,
            verdict=args.verdict,
            tokens=tokens,
        )
    except Exception as e:
        _warn(f"emit failed ({e})")
        return 0

    if not args.quiet:
        print(event_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
