"""Event ledger — append-only observability foundation.

Replaces fragmented signal carriers (validation-log heartbeats prose /
metrics.jsonl per-iter aggregates / per-script ad-hoc prints) with a
single append-only JSONL stream of lifecycle facts per engagement.

# Design choices

- Storage:           per-engagement `engagement/events.jsonl` (local, diffable,
                     portable). Not central SQLite — keeps the engagement
                     directory self-contained, matches whitelist semantics.
- Writer:            thin shared module (this file). Self-emitting scripts
                     drift; one shim gives schema enforcement, hashing,
                     timestamps, schema versioning in one place.
- Backfill:          forward-only. One synthetic `legacy_import` event if
                     ledger initialized on an engagement that already has
                     artefacts. Retroactive reconstruction = fake precision.
- Schema evolution:  event_schema_version + payload_type + payload_version +
                     replay adapters for old versions. Never mutate old events.
- Out of scope:      raw LLM I/O, full file contents, token traces, per-
                     validator sub-detail. Ledger stores lifecycle facts and
                     replay handles, not a second filesystem.

# Schema (v1)

Every event is a JSON object on one line in `engagement/events.jsonl`:

    {
      "event_id":             "ledger-v1-{ts}-{8charhex}",
      "event_schema_version": "1",
      "engagement_id":        "<dir-name>",
      "run_id":               "<uuid>",            # one per process invocation
      "tier":                 "S|M|L",
      "agent":                "dev-lead",          # who emitted
      "node":                 "phase:plan",        # logical position
      "payload_type":         "phase_completed",
      "payload_version":      "1",
      "payload":              { ... },             # type-specific body
      "input_hash":           "sha256:...",        # optional, for replay/dedup
      "output_schema_version":"1.0",               # for downstream consumers
      "verdict":              "ACCEPT|REJECT|N/A", # optional
      "interrupt_state":      "none|paused|resumed",
      "parent_event_id":      "<event_id or null>",
      "timestamp":            "2026-05-28T15:30:00.000000Z"
    }

# Payload types (v1 — extend as new emit sites land)

- legacy_import          synthetic; one per pre-ledger engagement
- ledger_initialized     first event on a fresh ledger
- engagement_started     lead's first action
- phase_started          lead begins a phase
- phase_completed        lead ends a phase
- specialist_dispatched  mid-lead spawns a specialist
- specialist_completed   specialist returns executor-report
- validator_started      validator_lg.py begins a validator
- validator_completed    validator_lg.py validator success
- validator_retried      validator_lg.py retry edge
- validator_failed       validator_lg.py terminal failure (after retry)
- barrier_passed         validator_lg.py barrier_node finished
- critical_check_paused  validator_lg.py interrupt() at critical_check_node
- critical_check_resumed validator_lg.py resumed via Command(resume=...)
- consilium_started      adversary_lg.py begins a reviewer
- consilium_role_completed
- consilium_synth_completed
- interrupt_paused       adversary_lg.py interrupt() at apply_directive_node
- interrupt_resumed      adversary_lg.py resumed via Command(resume=...)
- human_directive_received
- precheck_started       handoff-precheck.py begins a check
- precheck_passed
- precheck_failed
- handoff_submitted      lead final submission
- verdict_written        manager wrote acceptance-log verdict
- authority_conflict     blocking conflict per engagement-protocol §"Authority"
- reflection_emitted     manager appended to engagement-reflections.md
- signal_emitted         manager appended SIGNAL to skill-evolution-log.md
- heartbeat              lead phase heartbeat (replaces prose in validation-log)

# Usage

    from lib.ledger import EventLedger

    led = EventLedger(engagement_path, agent="dev-lead", tier="M")
    led.emit("phase_completed", node="phase:plan",
             payload={"phase": "plan", "duration_s": 12.4})
    # later:
    led.emit("validator_completed", node="run_validator",
             payload={"validator": "code-reviewer",
                      "verdict": "satisfied",
                      "findings_count": 2,
                      "elapsed_s": 18.1})

The constructor auto-emits `legacy_import` once if `events.jsonl` does not
exist and the engagement directory already has artefacts that predate the
ledger (criteria.md or any sibling). This is the only synthetic event ever
written; downstream consumers ignore it for analytics.

# Read-side

    from lib.ledger import EventLedger
    events = EventLedger.read(engagement_path)
    for e in events:
        ...

For schema evolution, callers should branch on `event_schema_version` and
`payload_version`. Old events are never mutated.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

# Module-level constants
EVENT_SCHEMA_VERSION = "1"
DEFAULT_PAYLOAD_VERSION = "1"
LEDGER_FILENAME = "events.jsonl"

# Known payload types — kept as a tuple so a typo at call site is caught early
# via assert. New payload types are added here as emit sites land. Order is
# significant only for `legacy_import` (must be first if used).
KNOWN_PAYLOAD_TYPES: tuple[str, ...] = (
    "legacy_import",
    "ledger_initialized",
    "engagement_started",
    "phase_started",
    "phase_completed",
    "specialist_dispatched",
    "specialist_completed",
    "validator_started",
    "validator_completed",
    "validator_retried",
    "validator_failed",
    "barrier_passed",
    "critical_check_paused",
    "critical_check_resumed",
    "consilium_started",
    "consilium_role_completed",
    "consilium_synth_completed",
    "interrupt_paused",
    "interrupt_resumed",
    "human_directive_received",
    "precheck_started",
    "precheck_passed",
    "precheck_failed",
    "handoff_submitted",
    "verdict_written",
    "authority_conflict",
    "reflection_emitted",
    "signal_emitted",
    "heartbeat",
    # engagement_lg.py
    "engagement_completed",   # final lifecycle event (ACCEPT/REJECT/ABORTED + duration)
    "phase_skipped",          # e.g. consilium for tier=S, archive for ABORTED
    "dryrun_marker",          # skeleton-mode banner: this run did no real work
)

ALLOWED_VERDICTS = {"ACCEPT", "REJECT", "DIRECTED", "N/A", None}
ALLOWED_INTERRUPT_STATES = {"none", "paused", "resumed"}
ALLOWED_TIERS = {"S", "M", "L", None}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _make_event_id() -> str:
    """Stable-looking ID: ledger-v1-{compact ts}-{8 hex}. Sortable by time."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    rand = uuid.uuid4().hex[:8]
    return f"ledger-v1-{ts}-{rand}"


class EventLedger:
    """Append-only writer for `engagement/events.jsonl`.

    Thread-safe within one process via a class-level lock around file open+
    write. Cross-process safety relies on OS append atomicity for lines
    smaller than PIPE_BUF (4096 bytes typical) — which all reasonable events
    are. Events larger than that should be split / linked via parent_event_id.

    Instances are cheap; create one per actor per phase if convenient,
    keeping `run_id` / `tier` / `agent` consistent so downstream filtering
    works without surprise.
    """

    _lock = threading.Lock()

    def __init__(
        self,
        engagement_path: os.PathLike | str,
        *,
        agent: str,
        tier: Optional[str] = None,
        run_id: Optional[str] = None,
        auto_init: bool = True,
    ):
        self.engagement = Path(engagement_path).resolve()
        if not self.engagement.exists() or not self.engagement.is_dir():
            raise ValueError(
                f"engagement directory not found or not a dir: {self.engagement}"
            )
        if tier is not None and tier not in ALLOWED_TIERS:
            raise ValueError(f"tier must be in {ALLOWED_TIERS}, got {tier!r}")
        self.agent = agent
        self.tier = tier
        self.run_id = run_id or uuid.uuid4().hex
        self._path = self.engagement / LEDGER_FILENAME
        self._initialized = self._path.exists()
        if auto_init and not self._initialized:
            self._initialize()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def engagement_id(self) -> str:
        return self.engagement.name

    # ---------------------------------------------------------------- emit

    def emit(
        self,
        payload_type: str,
        *,
        node: Optional[str] = None,
        payload: Optional[dict] = None,
        payload_version: str = DEFAULT_PAYLOAD_VERSION,
        input_hash: Optional[str] = None,
        output_schema_version: Optional[str] = None,
        verdict: Optional[str] = None,
        interrupt_state: str = "none",
        parent_event_id: Optional[str] = None,
        actor: Optional[str] = None,
    ) -> str:
        """Append one event. Returns the new event_id.

        actor: override `self.agent` for this single event (use when one
               process writes events on behalf of multiple agents, e.g.
               validator_lg.py emits validator-attributed events).
        """
        assert payload_type in KNOWN_PAYLOAD_TYPES, (
            f"unknown payload_type {payload_type!r}; "
            f"add to KNOWN_PAYLOAD_TYPES in lib/ledger.py first"
        )
        assert verdict in ALLOWED_VERDICTS, (
            f"verdict must be one of {ALLOWED_VERDICTS}, got {verdict!r}"
        )
        assert interrupt_state in ALLOWED_INTERRUPT_STATES, (
            f"interrupt_state must be one of {ALLOWED_INTERRUPT_STATES}, "
            f"got {interrupt_state!r}"
        )

        event_id = _make_event_id()
        event = {
            "event_id": event_id,
            "event_schema_version": EVENT_SCHEMA_VERSION,
            "engagement_id": self.engagement_id,
            "run_id": self.run_id,
            "tier": self.tier,
            "agent": actor or self.agent,
            "node": node,
            "payload_type": payload_type,
            "payload_version": payload_version,
            "payload": payload or {},
            "input_hash": input_hash,
            "output_schema_version": output_schema_version,
            "verdict": verdict,
            "interrupt_state": interrupt_state,
            "parent_event_id": parent_event_id,
            "timestamp": _utc_now_iso(),
        }
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        with EventLedger._lock:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        return event_id

    # --------------------------------------------------------------- helpers

    @staticmethod
    def hash_input(text: str) -> str:
        """Stable sha256 hex of a string. Use for `input_hash` field — pass
        the prompt / canonical input that drove this event so replay or
        dedup is possible later."""
        return _sha256_hex(text)

    def emit_authority_conflict(
        self,
        *,
        conflict_kind: str,
        sources: list[dict],
        resolution: Optional[str] = None,
        decided_by: Optional[str] = None,
        parent_event_id: Optional[str] = None,
    ) -> str:
        """Emit `authority_conflict` event for engagement-protocol §"Authority
        and conflict resolution" rule 6 enforcement.

        sources: list of {kind: "skill|agent|criteria|frontmatter|claude.md",
                          name: str, claim: str (≤200 chars)}
        conflict_kind: short tag, e.g. "skill_vs_agent_body",
                       "two_skills_overlap", "criteria_waives_protocol_gate",
                       "skill_version_drift_mid_engagement".
        resolution: outcome string (e.g. "skill wins per precedence rule 4",
                    "criteria.md added scope, no gate waiver needed",
                    "blocked — escalated to judge").
        decided_by: who decided ("auto-precedence", "judge", "<agent-name>").

        Use when dispatch detects conflicting instructions across sources.
        If resolution=None, the conflict is blocking — caller must halt
        before continuing (per rule 6: "Any unresolved conflict becomes a
        blocking authority_conflict event").
        """
        return self.emit(
            "authority_conflict",
            node="authority_check",
            payload={
                "conflict_kind": conflict_kind,
                "sources": sources,
                "resolution": resolution,
                "decided_by": decided_by,
                "blocking": resolution is None,
            },
            verdict=("REJECT" if resolution is None else None),
            parent_event_id=parent_event_id,
        )

    def emit_skill_snapshot(
        self,
        *,
        skills: list[dict],
        parent_event_id: Optional[str] = None,
    ) -> str:
        """Emit a snapshot of loaded skills at engagement start (engagement-
        protocol §"Authority and conflict resolution" rule 7 enforcement).

        skills: list of {name: str, version: str|None,
                         content_hash: str (sha256:...)|None,
                         path: str (relative)}

        Producer (typically lead at Phase 1 dispatch) walks
        `~/.claude/skills/*/SKILL.md`, computes sha256 of body, records the
        list once. Subsequent skill edits mid-engagement do not apply unless
        the human judge approves + records a new snapshot (next phase).
        """
        return self.emit(
            "engagement_started",
            node="skill_snapshot",
            payload={
                "skills_snapshot": skills,
                "skill_count": len(skills),
            },
            parent_event_id=parent_event_id,
        )

    @staticmethod
    def snapshot_skills(skills_dir: os.PathLike | str) -> list[dict]:
        """Walk `~/.claude/skills/*/SKILL.md`, return canonical snapshot list
        (name + sha256 hash + path). Use to feed emit_skill_snapshot()."""
        sd = Path(skills_dir).resolve()
        if not sd.exists() or not sd.is_dir():
            return []
        out: list[dict] = []
        for skill_dir in sorted(sd.iterdir()):
            if not skill_dir.is_dir():
                continue
            sm = skill_dir / "SKILL.md"
            if not sm.exists():
                continue
            try:
                body = sm.read_text(encoding="utf-8")
            except Exception:
                continue
            out.append({
                "name": skill_dir.name,
                "version": None,  # explicit version field not yet in frontmatter
                "content_hash": "sha256:" + _sha256_hex(body),
                "path": str(sm),
                "lines": body.count("\n") + 1,
            })
        return out

    # --------------------------------------------------------------- read

    @classmethod
    def read(cls, engagement_path: os.PathLike | str) -> list[dict]:
        """Read all events in append order. Returns [] if ledger missing."""
        p = Path(engagement_path).resolve() / LEDGER_FILENAME
        if not p.exists():
            return []
        out: list[dict] = []
        for ln in p.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                # Skip corrupt line; surface via stderr but don't blow up.
                print(f"WARN: corrupt ledger line in {p}: {ln[:120]!r}",
                      file=sys.stderr)
        return out

    @classmethod
    def iter_(cls, engagement_path: os.PathLike | str) -> Iterable[dict]:
        """Iterator variant — useful for very long ledgers."""
        p = Path(engagement_path).resolve() / LEDGER_FILENAME
        if not p.exists():
            return
        with p.open("r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    yield json.loads(ln)
                except json.JSONDecodeError:
                    print(f"WARN: corrupt ledger line in {p}: {ln[:120]!r}",
                          file=sys.stderr)

    # -------------------------------------------------------------- private

    def _initialize(self) -> None:
        """First-time setup: write `ledger_initialized` (always) + optional
        synthetic `legacy_import` if the engagement directory already had
        artefacts. The synthetic event carries no replayable detail — it is
        purely a marker so downstream consumers can detect pre-ledger gaps."""
        # legacy_import is implicit: did the engagement exist before us?
        # We use criteria.md / handoff.md / acceptance-log.md presence as a
        # proxy. Absence of all three = brand-new engagement, no legacy.
        legacy_signals = [
            (self.engagement / "criteria.md").exists(),
            (self.engagement / "handoff.md").exists(),
            (self.engagement / "acceptance-log.md").exists(),
            (self.engagement / "executor-reports").exists(),
        ]
        had_legacy = any(legacy_signals)
        if had_legacy:
            self._raw_append({
                "event_id": _make_event_id(),
                "event_schema_version": EVENT_SCHEMA_VERSION,
                "engagement_id": self.engagement_id,
                "run_id": self.run_id,
                "tier": self.tier,
                "agent": self.agent,
                "node": None,
                "payload_type": "legacy_import",
                "payload_version": DEFAULT_PAYLOAD_VERSION,
                "payload": {
                    "note": "engagement existed before ledger; pre-ledger "
                            "lifecycle reconstruction is not attempted.",
                    "had_criteria_md": legacy_signals[0],
                    "had_handoff_md": legacy_signals[1],
                    "had_acceptance_log": legacy_signals[2],
                    "had_executor_reports": legacy_signals[3],
                },
                "input_hash": None,
                "output_schema_version": None,
                "verdict": None,
                "interrupt_state": "none",
                "parent_event_id": None,
                "timestamp": _utc_now_iso(),
            })
        # Always emit ledger_initialized so the first ledger byte names the
        # writer + run_id. Useful for "who started this run".
        self._raw_append({
            "event_id": _make_event_id(),
            "event_schema_version": EVENT_SCHEMA_VERSION,
            "engagement_id": self.engagement_id,
            "run_id": self.run_id,
            "tier": self.tier,
            "agent": self.agent,
            "node": None,
            "payload_type": "ledger_initialized",
            "payload_version": DEFAULT_PAYLOAD_VERSION,
            "payload": {
                "writer": "lib.ledger.EventLedger",
                "had_legacy_marker": had_legacy,
            },
            "input_hash": None,
            "output_schema_version": None,
            "verdict": None,
            "interrupt_state": "none",
            "parent_event_id": None,
            "timestamp": _utc_now_iso(),
        })
        self._initialized = True

    def _raw_append(self, event: dict) -> None:
        """Bypass the assert checks — used internally for synthetic events
        whose `payload_type` is in KNOWN_PAYLOAD_TYPES by definition."""
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        with EventLedger._lock:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")


# Convenience module-level helper for one-shot emits (no instance reuse).
def emit_one(
    engagement_path: os.PathLike | str,
    agent: str,
    payload_type: str,
    *,
    tier: Optional[str] = None,
    **kwargs,
) -> str:
    """Single-event convenience. For multi-event flows, instantiate the
    EventLedger class directly to reuse run_id + tier + agent."""
    led = EventLedger(engagement_path, agent=agent, tier=tier)
    return led.emit(payload_type, **kwargs)
