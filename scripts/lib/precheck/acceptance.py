"""Director-side acceptance artefact checks.

Five checks live here:
  - check_acceptance_log_paths: paths cited in acceptance-log.md exist
    (criteria-trace evidence). Delegates to handoff-paths-check.py.
  - check_verdict_canonical: acceptance-log.md uses canonical
    `### Verdict: ACCEPT|REJECT|ABORTED` format; warn on legacy forms.
  - check_human_directive: human-directive.md present + parseable Decision
    line, gated on consilium-summary.md existing.
  - check_consilium_addressed: an M/L verdict either has the consilium, or
    says why it does not.
  - check_director_verdict: delegate to director-verdict-check.py for
    consilium-signal adjudication completeness.
  - check_handoff_digest: the latest verdict is bound to the sha256 of the
    handoff it was written against, so a handoff edited after acceptance (or
    reworked without bumping the iteration) stops reading as approved.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .common import handoff_digest, read_iteration_counter, run

HUMAN_DIRECTIVE_DECISIONS = {"PROCEED_TO_VERDICT", "REJECT_NOW", "DIRECTED_VERDICT"}


def check_acceptance_log_paths(eng: Path, scripts_dir: Path) -> dict:
    """Verify paths cited in acceptance-log.md exist (criteria-trace evidence)."""
    log = eng / "acceptance-log.md"
    if not log.exists():
        return {"name": "acceptance-log-paths", "status": "skip", "detail": "acceptance-log.md not yet written"}
    text = log.read_text(encoding="utf-8")
    if "Verdict: ACCEPT" not in text:
        return {"name": "acceptance-log-paths", "status": "skip", "detail": "no ACCEPT verdict yet — only relevant after director writes ACCEPT"}
    code, out = run([sys.executable, str(scripts_dir / "handoff-paths-check.py"), str(log), "--json"])
    try:
        data = json.loads(out)
        if data.get("status") == "pass":
            return {"name": "acceptance-log-paths", "status": "pass", "detail": f"{data.get('total_cited', 0)} cited paths in ACCEPT verdict exist"}
        missing = [p["path"] for p in data.get("paths", []) if not p.get("exists")]
        return {"name": "acceptance-log-paths", "status": "fail", "detail": f"phantom paths in ACCEPT criteria trace: {missing}"}
    except json.JSONDecodeError:
        return {"name": "acceptance-log-paths", "status": "fail", "detail": f"check script error (exit {code}): {out[:200]}"}


def check_verdict_canonical(eng: Path) -> dict:
    """Acceptance-log must contain canonical `### Verdict: ACCEPT|REJECT|ABORTED`.

    Legacy formats (`**ACCEPTED**`, `# Verdict: ACCEPT — ...`, "engagement is CLOSED")
    are still accepted by archive script for backward compat, but new engagements
    MUST write the canonical form so machine-parsers stay reliable. WARN on legacy.
    """
    log = eng / "acceptance-log.md"
    if not log.exists():
        return {"name": "verdict-canonical", "status": "skip", "detail": "acceptance-log.md not yet written"}
    text = log.read_text(encoding="utf-8")

    canonical = re.search(r"^###\s+Verdict:\s+(ACCEPT|REJECT|ABORTED)\b", text, re.MULTILINE)
    if canonical:
        return {"name": "verdict-canonical", "status": "pass", "detail": f"canonical verdict found: {canonical.group(1)}"}

    # Detect legacy forms — these still archive (Tier 11.1 flexibility) but signal drift
    legacy_patterns = [
        (r"^\*\*ACCEPTED?\*\*", "**ACCEPTED**"),
        (r"^Verdict[:\s]+ACCEPT(?:ED)?", "Verdict: ACCEPTED"),
        (r"^#\s+Verdict:", "# Verdict (H1 instead of H3)"),
        (r"^##\s+Verdict\s*$", "## Verdict (no body)"),
        (r"engagement\s+\S+\s+is\s+\*?\*?CLOSED", "engagement is CLOSED"),
    ]
    for pat, label in legacy_patterns:
        if re.search(pat, text, re.MULTILINE | re.IGNORECASE):
            return {
                "name": "verdict-canonical",
                "status": "warn",
                "detail": f"legacy verdict format detected ({label}); canonical is `### Verdict: ACCEPT|REJECT|ABORTED`",
                "fix": "Director: write `### Verdict: ACCEPT` (or REJECT / ABORTED) on its own line. Archive still works on legacy, but machine-readability degrades.",
            }

    return {
        "name": "verdict-canonical",
        "status": "fail",
        "detail": "acceptance-log.md exists but no parseable verdict found",
        "fix": "Director must write `### Verdict: ACCEPT|REJECT|ABORTED`.",
    }


def check_human_directive(eng: Path) -> dict:
    """Verify human-directive.md presence and structure for M/L tiers.

    Flow: after consilium-synth.py produces consilium-summary.md, human reads
    it and writes human-directive.md with one of three decisions. Director
    then writes verdict per directive.

    Skipped if consilium-summary.md doesn't exist yet (consilium hasn't run).
    """
    consilium = eng / "consilium-summary.md"
    directive = eng / "human-directive.md"
    log = eng / "acceptance-log.md"

    if not consilium.exists():
        return {"name": "human-directive", "status": "skip", "detail": "consilium-summary.md missing — consilium not yet run"}

    if not directive.exists():
        # If acceptance-log.md exists, director wrote verdict without directive — fail
        if log.exists():
            return {
                "name": "human-directive",
                "status": "fail",
                "detail": "consilium ran but human-directive.md absent AND director already wrote verdict",
                "fix": "Per protocol: human reads consilium-summary.md, writes human-directive.md (PROCEED_TO_VERDICT | REJECT_NOW | DIRECTED_VERDICT), THEN director writes verdict. Director skipped human-judge step.",
            }
        return {"name": "human-directive", "status": "skip", "detail": "consilium done; awaiting human directive (this is normal mid-acceptance)"}

    text = directive.read_text(encoding="utf-8")
    decision_match = re.search(r"^Decision:\s*(\w+)", text, re.MULTILINE)
    if not decision_match:
        return {
            "name": "human-directive",
            "status": "fail",
            "detail": "human-directive.md present but no parseable `Decision:` line",
            "fix": "human-directive.md must include a line `Decision: PROCEED_TO_VERDICT | REJECT_NOW | DIRECTED_VERDICT`.",
        }
    decision = decision_match.group(1).upper().strip()
    if decision not in HUMAN_DIRECTIVE_DECISIONS:
        return {
            "name": "human-directive",
            "status": "fail",
            "detail": f"human-directive.md Decision={decision} not in {sorted(HUMAN_DIRECTIVE_DECISIONS)}",
            "fix": f"Set Decision to one of {sorted(HUMAN_DIRECTIVE_DECISIONS)}.",
        }
    return {"name": "human-directive", "status": "pass", "detail": f"directive present, Decision={decision}"}


ADVERSARY_ROLES = ("peer-opus", "codex-blind", "codex-informed", "codex-crossfamily",
                   "sonnet-scoped", "haiku-scoped")
# A legitimate non-run says so. The subject (consilium / adversary) and the disposition must
# appear IN THE SAME SENTENCE. An earlier version matched them within 120 characters of a
# whitespace-collapsed document, which a cross-family review broke in one line: "The consilium
# is listed in criteria. Instead of changing the footer, the team changed the logo." passed the
# gate on a collision between two unrelated sentences. Sentence scope is what makes the two
# halves actually refer to each other.
_SUBJECT = r"(?:consilium|adversar\w*)"
# Three dispositions count as addressing it: waived by authority, could not run, or was
# substituted by something the acceptor names. The third was learned from a false positive:
# an M-tier log that said "in lieu of a separately spun consilium-M workflow, the acceptor
# performed direct independent verification" was flagged, though it addresses the consilium
# as squarely as the ones that say "NOT run".
# The `(?<!not )(?<!never )` guards keep a NEGATED disposition from counting as one: "the
# consilium was not skipped; it ran, but its JSON was lost" says the opposite of a non-run and
# used to pass the gate.
_DISPOSITION = (r"(?:waiv\w*|overrid\w*|did\s+not\s+run|does\s+not\s+run|not\s+run|"
                r"could\s+not\s+run|unavailable|(?<!not )(?<!never )skipp\w*|omitt\w*|"
                r"not\s+performed|in\s+lieu\s+of|instead\s+of|"
                r"(?<!not )(?<!never )substitut\w*|stood\s+in\s+for|"
                r"stand(?:ing)?\s+in\s+for)")
# A shape neither ordering catches on its own: the negation attached directly to the subject
# ("no consilium/adversary run", "without an adversary phase").
_NEGATED_SUBJECT = rf"(?:no|without)\s+[\w/\-]{{0,20}}\s*{_SUBJECT}[\w/\- ]{{0,30}}?\b(?:run|dispatch|phase|pass)\b"
# Two tiers, because neither distance nor clause boundaries work alone.
#
# Distance alone fails: real disclosures span up to 104 characters between subject and
# disposition, and a constructed false positive spans 101.
#
# Clause splitting alone fails in the other direction: "The consilium was attempted AND could
# not run because the stack was unavailable" is one legitimate disclosure whose halves sit on
# opposite sides of the conjunction.
#
# So: a match inside one CLAUSE may span the whole clause (_GAP), and a match that crosses a
# clause boundary must be TIGHT (_GAP_TIGHT) — close enough that the disposition is still
# plainly about the consilium. 60 characters admits "consilium was attempted and could not
# run" and rejects "consilium is merely mentioned in the historical background, with the
# unrelated deployment phase skipped".
_GAP = r"[^\n]{0,200}?"
_GAP_TIGHT = r"[^\n]{0,60}?"
CONSILIUM_DISPOSITION_RE = re.compile(
    rf"{_NEGATED_SUBJECT}|{_SUBJECT}{_GAP}{_DISPOSITION}|{_DISPOSITION}{_GAP}{_SUBJECT}",
    re.IGNORECASE)
CONSILIUM_DISPOSITION_TIGHT_RE = re.compile(
    rf"{_NEGATED_SUBJECT}|{_SUBJECT}{_GAP_TIGHT}{_DISPOSITION}|{_DISPOSITION}{_GAP_TIGHT}{_SUBJECT}",
    re.IGNORECASE)
# Split on sentence enders followed by whitespace, and on coordinating conjunctions that start
# a new clause. A filename like `adversary_lg.py --consilium` is untouched because its dot is
# followed by a letter, not a space. `and` is a real cut point here: "no recursive sub-agent
# dispatch and no consilium/adversary run" keeps its disposition on the consilium side of the
# cut, while "the consilium is mentioned and <unrelated clause about a substitution>" does not.
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?;])\s+")
CLAUSE_SPLIT_RE = re.compile(
    r"(?<=[.!?;])\s+"
    r"|\s+(?:and|but|while|whereas|however)\s+"
    # A comma followed by a relative or resultative connector starts a new clause too:
    # "the consilium is merely mentioned in the historical background, WITH the unrelated
    # deployment phase skipped" has no conjunction and no sentence end, so nothing else cuts it.
    r"|,\s+(?:with|which|where|whose|so|though|although)\s+",
    re.IGNORECASE)


def disposition_match(text: str):
    """A disposition that is actually ABOUT the consilium, not merely near it.

    Accepts either: both halves inside one clause, at any distance up to _GAP; or both halves
    inside one sentence but close together (_GAP_TIGHT), which is what lets a disclosure
    survive a conjunction without letting an unrelated clause supply the disposition.
    """
    flat = re.sub(r"\s+", " ", text)
    for clause in CLAUSE_SPLIT_RE.split(flat):
        m = CONSILIUM_DISPOSITION_RE.search(clause)
        if m:
            return m
    for sentence in SENTENCE_SPLIT_RE.split(flat):
        m = CONSILIUM_DISPOSITION_TIGHT_RE.search(sentence)
        if m:
            return m
    return None


def check_consilium_addressed(eng: Path, size: str) -> dict:
    """On M/L, a written verdict must not leave the consilium unmentioned.

    check_human_directive SKIPs whenever consilium-summary.md is absent, reading that as
    "the consilium has not run YET". That reading never expires: an engagement that never
    runs it skips the check forever, and nothing downstream asks whether it should have.
    Measured 2026-08-27 over 11 archived L-tier engagements, 3 were accepted with no
    adversary artefacts at all. Two were legitimate and said so in plain text (a
    user-directed waiver recorded in criteria.md; a disclosed non-run when the subprocess
    stack was unavailable). The third declared a mandatory cross-family consilium in its
    criteria, was accepted, and its acceptance-log does not mention the consilium in any
    form. That is the silent-skip class the 2026-06-01 `rule_ignored` signal predicted.

    So this gate does not require the consilium to have RUN — that would false-REJECT the
    two legitimate cases, which is exactly why the provenance gate was deferred in the
    first place. It requires the verdict to ADDRESS it: proof-of-run, or a summary, or a
    sentence saying why neither exists.

    Skips until a verdict exists; before that, absence means "not yet" for real.
    """
    if size not in ("M", "L"):
        return {"name": "consilium-addressed", "status": "skip",
                "detail": f"tier {size} has no consilium phase"}
    log = eng / "acceptance-log.md"
    if not log.exists():
        return {"name": "consilium-addressed", "status": "skip",
                "detail": "no verdict written yet — consilium may still be pending"}

    vo = eng / "validation-outputs"
    # Anchor the role at the START of the filename. Every real adversary output is named
    # `<role>-iter-N-<stamp>.json`; a plain substring test would accept an ordinary validator
    # file that merely contains a role name, e.g. `validator-peer-opus-review.json`.
    # Role at the START of the name AND an `iter` marker: every real adversary output is
    # `<role>-iter-N-<stamp>.json` or `<role>-...-iterN-<stamp>.json`. Prefix alone would still
    # accept a hand-named `peer-opus-validator-review.json`.
    proof = sorted(p.name for p in vo.glob("*.json")
                   if p.is_file()
                   and any(p.name.lower().startswith(r) for r in ADVERSARY_ROLES)
                   and "iter" in p.name.lower()) if vo.is_dir() else []
    if proof:
        return {"name": "consilium-addressed", "status": "pass",
                "detail": f"{len(proof)} adversary role output(s), e.g. {proof[0]}"}
    summary = eng / "consilium-summary.md"
    # Non-empty is the whole bar, and `.exists()` alone would also accept a directory of that
    # name. A length floor was tried and removed: at 40 characters it rejected the legitimate
    # terse summary "Waived by human; no consilium run." while still admitting a longer
    # placeholder, so it bought nothing and cost a false REJECT. Whether the summary actually
    # adjudicates every consilium signal is `director-verdict`'s job, not this gate's.
    if summary.is_file() and summary.read_text(encoding="utf-8", errors="replace").strip():
        return {"name": "consilium-addressed", "status": "pass",
                "detail": "consilium-summary.md present (no per-role JSON in validation-outputs/)"}

    for source in (log, eng / "criteria.md"):
        if source.exists():
            # Whitespace is collapsed inside disposition_match(): these documents wrap at ~100
            # columns, so the subject and its disposition routinely land on different lines
            # ("In lieu of a separately / spun consilium-M workflow").
            m = disposition_match(source.read_text(encoding="utf-8", errors="replace"))
            if m:
                return {"name": "consilium-addressed", "status": "pass",
                        "detail": f"non-run disclosed in {source.name}: {m.group(0)[:90].strip()!r}"}

    return {
        "name": "consilium-addressed",
        "status": "fail",
        "detail": f"tier {size} verdict written with no adversary output, no consilium-summary.md, "
                  "and no stated reason for either",
        "fix": "Run the consilium (`adversary_lg.py --consilium M|L`) before the verdict, or state "
               "in acceptance-log.md / criteria.md that it was waived or could not run, and why. "
               "An unmentioned consilium is indistinguishable from a forgotten one.",
    }


def check_director_verdict(eng: Path, scripts_dir: Path) -> dict:
    """Run director-verdict-check.py — verify director adjudicated all consilium signals.

    Skipped if acceptance-log.md doesn't exist yet (director hasn't written) or
    consilium-summary.md doesn't exist (M/L acceptance hasn't run consilium yet).
    """
    checker = scripts_dir / "director-verdict-check.py"
    if not checker.exists():
        return {"name": "director-verdict", "status": "skip", "detail": "director-verdict-check.py not installed"}
    code, out = run([sys.executable, str(checker), str(eng), "--json"])
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return {"name": "director-verdict", "status": "skip", "detail": f"checker output unparseable: {out[:160]}"}
    status = data.get("status", "skip")
    if status == "skip":
        return {"name": "director-verdict", "status": "skip", "detail": data.get("detail", "")}
    if status == "fail":
        return {
            "name": "director-verdict",
            "status": "fail",
            "detail": "; ".join(data.get("issues", []))[:200],
            "fix": "Director must mark each consilium signal in acceptance-log.md: SUSTAINED/OVERRULED for convergent, SIDED WITH X for cross-family disagreements, REAL/FALSE_POSITIVE for naive catches, ACKNOWLEDGED for too-clean flags.",
        }
    return {"name": "director-verdict", "status": "pass", "detail": "all consilium signals adjudicated"}


_ITER_HEADING_RE = re.compile(r"^##\s*Iteration\s+(\d+)\b", re.MULTILINE | re.IGNORECASE)
_VERDICT_RE = re.compile(r"^###\s+Verdict:\s+(ACCEPT|REJECT|ABORTED)\b", re.MULTILINE)
_DIGEST_RE = re.compile(r"handoff-sha256\s*[:=]\s*`?([0-9a-fA-F]{64})`?")


def _acceptance_log_sections(text: str) -> list[tuple[int, str]]:
    """Split acceptance-log.md into (iteration_number, section_text) pairs.

    Text before the first `## Iteration N` heading is dropped: a verdict there
    has no iteration to bind to, and check_iteration_counter already owns the
    "log has no iteration headings" complaint.
    """
    marks = list(_ITER_HEADING_RE.finditer(text))
    out: list[tuple[int, str]] = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out.append((int(m.group(1)), text[m.start():end]))
    return out


def check_handoff_digest(eng: Path) -> dict:
    """A verdict must be bound to the exact handoff it was written against.

    Without this, a verdict is bound to nothing: handoff.md can be edited after
    an ACCEPT, or reworked in place without bumping the iteration counter, and
    the recorded verdict still reads as current. The engagement then carries an
    approval of content that is no longer in the file.

    Deliberately narrow so it cannot false-fail an engagement predating it:

      - no handoff.md / no acceptance-log.md / no verdict yet -> skip
      - verdict exists but no digest recorded  -> warn, with the exact line to
        paste and the digest already computed
      - recorded == current                    -> pass
      - recorded != current, verdict is from an EARLIER iteration -> pass
        (rework is supposed to change the handoff)
      - recorded != current, verdict is for the CURRENT iteration -> fail
      - recorded != current, iteration unknown -> warn, never fail: without the
        counter, rework cannot be told apart from an edit after the fact

    Scope limit, stated plainly: the digest covers handoff.md only, not every
    artefact it cites. It catches a changed handoff, not a changed screenshot.
    """
    name = "handoff-digest"
    current = handoff_digest(eng)
    if current is None:
        return {"name": name, "status": "skip", "detail": "handoff.md not written yet"}

    short = current[:12]
    record_line = f"handoff-sha256: {current}"

    log = eng / "acceptance-log.md"
    if not log.exists():
        return {"name": name, "status": "skip",
                "detail": f"no acceptance-log.md yet; current handoff digest {short}"}

    text = log.read_text(encoding="utf-8", errors="replace")
    sections = [(n, body) for n, body in _acceptance_log_sections(text)
                if _VERDICT_RE.search(body)]
    if not sections:
        return {"name": name, "status": "skip",
                "detail": f"no verdict written yet; current handoff digest {short}"}

    iter_n, body = max(sections, key=lambda pair: pair[0])
    recorded = _DIGEST_RE.search(body)

    if not recorded:
        return {
            "name": name, "status": "warn",
            "detail": f"verdict for iteration {iter_n} is not bound to a handoff digest, "
                      f"so nothing detects the handoff changing under it",
            "fix": f"Add this line inside the `## Iteration {iter_n}` section of acceptance-log.md, "
                   f"next to the verdict: `{record_line}` "
                   f"(the digest of the handoff artefacts as of this iteration).",
        }

    recorded_hex = recorded.group(1).lower()
    if recorded_hex == current:
        return {"name": name, "status": "pass",
                "detail": f"iteration {iter_n} verdict bound to current handoff ({short})"}

    counter = read_iteration_counter(eng)
    if counter is not None and iter_n < counter:
        return {"name": name, "status": "pass",
                "detail": f"latest verdict is from iteration {iter_n}, engagement is on {counter}; "
                          f"the handoff changed during rework, which is expected"}

    if counter is None:
        return {
            "name": name, "status": "warn",
            "detail": f"handoff digest {short} does not match the one recorded for the iteration "
                      f"{iter_n} verdict ({recorded_hex[:12]}), and engagement/iteration is missing "
                      f"or unparseable, so rework cannot be told apart from a later edit",
            "fix": "Restore engagement/iteration, then re-run. If the handoff was legitimately "
                   f"reworked, bump the counter; if the verdict still stands, re-record `{record_line}`.",
        }

    return {
        "name": name, "status": "fail",
        "detail": f"handoff.md changed after the iteration {iter_n} verdict was written: recorded "
                  f"{recorded_hex[:12]}, current {short}. The verdict approves content that is no "
                  f"longer in the file.",
        "fix": "Either revert handoff.md to what the verdict was written against, or treat this as "
               "a new iteration (bump engagement/iteration, re-submit, get a fresh verdict). If the "
               f"edit was immaterial and the verdict stands, re-record it deliberately: `{record_line}`.",
    }
