#!/usr/bin/env python3
"""Regression guard — class_key() in skillopt-ready.py and harness-ready.py.

Both self-improvement loops fire on a count of signals sharing a (domain|script, class) key.
The class comes from the free-text `Failure class:` line of a signal, normalised by class_key().
Two authoring conventions were supported:

  A  "descriptive-slug (rule_token)"   -> slug          (the trailing token is stripped)
  B  "rule_token free prose"           -> token         (the prose is dropped)

Anything else fell through to the WHOLE LINE as the key: most `Failure class:` lines fell
through, producing almost one distinct key per signal. A key
that is unique by construction can never reach a threshold, so both loops were structurally
unable to fire regardless of what the field produced. The concrete loss: three signals written
as "tooling false-negative (<instance>)" describe one class and never clustered.

Pinned here:

  A. HEAD IS THE KEY     a line whose taxonomy slug is followed by a parenthetical, a dash
                         clause or a second sentence keys on the slug alone.
  B. CONVENTIONS HOLD    the two previously supported forms keep their existing keys, so no
                         historical bucket silently re-partitions.
  C. NO OVER-MERGE       two different taxonomy slugs stay in different buckets. The head rule
                         drops the INSTANCE, never the CLASS.
  D. MIRRORED            both scripts return identical keys for identical input. They cluster
                         the same log; a divergence splits one problem across two loops.
  E. REKEY WINS          a triage `rekey: <date> - as <slug> (<rule_x>)` line (system-
                         optimization-protocol §Triage item 4) overrides the key of its signal;
                         the latest one wins; a malformed one is ignored; an un-rekeyed
                         Convention-B signal keeps its bare-token key. Without it, a triage
                         that splits `rule_missing (<prose>)` signals into separate classes is
                         ignored, and the hook keeps reporting a cycle the triage disproved.

Run standalone or under pytest:
  python test_class_key_regress.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


skillopt = _load("_skillopt_ready", "skillopt-ready.py")
harness = _load("_harness_ready", "harness-ready.py")

# `Failure class:` lines in the shapes the convention-C cut must handle.
FELL_THROUGH = [
    ("tooling false-negative (host-level pg_isready cannot reach a compose-network-only "
     "Postgres)", "tooling false-negative"),
    ("tooling false-negative (host-level redis-cli cannot reach a compose-network-only Redis) "
     "— same class as the Postgres one", "tooling false-negative"),
    ("tooling false-negative (codex reviewer roles produced no output → consilium-summary "
     "framed it as agreement)", "tooling false-negative"),
    ("verification-coverage-gap (rule_wrong) — the exercised / real-HTTP verification "
     "requirement was scoped to ux_heavy only", "verification-coverage-gap"),
    ("workflow-doctrine-gap (rule_missing) — when an exercised-verification task discovers a "
     "BLOCKING defect outside scope", "workflow-doctrine-gap"),
    ("orchestration-engine-bug (the engagement-workflow consolidates wave commits onto the "
     "checked-out local `main`)", "orchestration-engine-bug"),
    ("gate-false-positive (handoff-gate size-detect diffs vs the BOOTSTRAP commit)",
     "gate-false-positive"),
    ("security-gap (rate-limit)", "security-gap"),
    ("consilium-summary misrepresents the captured consilium (verdict-provenance drift). "
     "SHARPER variant of the deferred provenance-gate concern.",
     "consilium-summary misrepresents the captured consilium"),
]

# Forms that already worked. Their keys must not move.
STABLE = [
    ("intake-size-misclassification (rule_wrong)", "intake-size-misclassification"),
    ("rule_ignored (mandatory M-tier consilium silently skipped)", "rule_ignored"),
    ("rule_ignored", "rule_ignored"),
    ("spec-code-drift", "spec-code-drift"),
    ("flaky-test-masking", "flaky-test-masking"),
    ("token-drift", "token-drift"),
]

# A colon is NOT a split point, and that is deliberate. A cross-family review first asked for
# it (colon-style instances under-merge), then showed the cost: `config: authentication failure`
# and `config: authorization failure` would both key to `config`. A colon separates a category
# from a discriminator at least as often as it separates a class from an instance, and the
# signal conventions do not use the style. Under-merging is the safe direction here:
# it costs a cluster that the domain-backlog trigger still surfaces, while over-merging hands
# the director a bucket whose members share nothing.
COLON_STYLE_STAYS_SPLIT = [
    "tooling false-negative: pg_isready cannot reach compose Postgres",
    "tooling false-negative: redis-cli cannot reach compose Redis",
    "config: authentication failure",
    "config: authorization failure",
]

# Distinct classes that must not collapse into one another.
DISTINCT = [
    "tooling false-negative (pg_isready)",
    "tooling/platform-limitation (nested dispatch is dead)",
    "gate-false-positive (size-detect)",
    "orchestration-engine-bug (wave commits)",
    "spec-code-drift",
]


# Four signal blocks shaped like the 2026-10-09 dev triage. Traced to a skill AND the engine so
# both checkers parse them. Order matters: the tests index into parse_signals() output.
REKEY_LOG = """\
### SIGNAL | domain: dev | 2026-10-06 | engagement: eng-a
Failure class: rule_missing (validate-phase changes_required does not block handoff)
Traced to: workflows/engagement-workflow.js + skills/validation-pipeline
rekey: 2026-10-09 - as validator-finding-deferred-without-waiver (rule_wrong). Not rule_missing.

### SIGNAL | domain: dev | 2026-10-06 | engagement: eng-a
Failure class: rule_missing (same-family validators miss false-pass classes)
Traced to: workflows/engagement-workflow.js + skills/validation-pipeline
rekey: 2026-10-20 - as decision-function-false-pass-probing-gap (rule_missing). Later triage.
rekey: 2026-10-09 - as some-earlier-guess (rule_wrong). Written below, but dated earlier.

### SIGNAL | domain: dev | 2026-10-06 | engagement: eng-a
Failure class: rule_missing (an untriaged signal)
Traced to: workflows/engagement-workflow.js + skills/validation-pipeline

### SIGNAL | domain: dev | 2026-10-06 | engagement: eng-a
Failure class: rule_missing (a signal with a malformed rekey)
Traced to: workflows/engagement-workflow.js + skills/validation-pipeline
rekey: someday maybe as a better name
"""


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok and detail:
        print(f"         {detail}")
    return ok


def main() -> int:
    results = []

    print("A. head is the key (fell-through lines)")
    for raw, want in FELL_THROUGH:
        got = skillopt.class_key(raw)
        results.append(check(f"{want!r}", got == want, f"got {got!r}\n         from {raw[:70]!r}"))

    print("\nA2. a colon is not a split point (deliberate — see the note above)")
    keys = [skillopt.class_key(r) for r in COLON_STYLE_STAYS_SPLIT]
    results.append(check("colon-style classes keep their full string as the key",
                         all(":" in k for k in keys), f"keys: {keys}"))
    results.append(check("`config: authn` and `config: authz` do NOT collapse to `config`",
                         keys[2] != keys[3] and keys[2] != "config", f"keys: {keys[2:]}"))

    print("\nB. previously supported conventions unchanged")
    for raw, want in STABLE:
        got = skillopt.class_key(raw)
        results.append(check(f"{want!r}", got == want, f"got {got!r}"))

    print("\nC. no over-merge")
    keys = [skillopt.class_key(x) for x in DISTINCT]
    results.append(check(f"{len(DISTINCT)} distinct classes stay distinct",
                         len(set(keys)) == len(DISTINCT), f"keys: {keys}"))

    print("\nC2. a KNOWN, accepted over-merge — recorded so it stays a decision, not a surprise")
    ym = skillopt.class_key("config-parser (YAML syntax)")
    tm = skillopt.class_key("config-parser (TOML syntax)")
    results.append(check("parenthetical treated as the instance: both key to 'config-parser'",
                         ym == tm == "config-parser", f"got {ym!r} / {tm!r}"))
    print("       Accepted because a director reads every signal in a bucket before proposing")
    print("       an edit, while under-merging leaves the loop mute. Revisit if a real bucket")
    print("       ever mixes causes.")

    print("\nD. both checkers agree")
    for raw in [r for r, _ in FELL_THROUGH + STABLE] + COLON_STYLE_STAYS_SPLIT + DISTINCT:
        a, b = skillopt.class_key(raw), harness.class_key(raw)
        results.append(check(f"mirror {a!r}", a == b, f"skillopt={a!r} harness={b!r}"))

    print("\nE. a triage rekey line overrides the class (both checkers)")
    for name, mod in (("skillopt", skillopt), ("harness", harness)):
        got = [s["class_key"] for s in mod.parse_signals(REKEY_LOG)]
        results.append(check(f"{name}: rekeyed signal keys on the rekey slug",
                             got[0] == "validator-finding-deferred-without-waiver", f"got {got[0]!r}"))
        results.append(check(f"{name}: the LATEST rekey wins (by date, not position)",
                             got[1] == "decision-function-false-pass-probing-gap", f"got {got[1]!r}"))
        results.append(check(f"{name}: an un-rekeyed Convention-B signal keeps the bare token",
                             got[2] == "rule_missing", f"got {got[2]!r}"))
        results.append(check(f"{name}: a malformed rekey line is ignored",
                             got[3] == "rule_missing", f"got {got[3]!r}"))
        results.append(check(f"{name}: the three triaged-shape signals no longer share one key",
                             len({got[0], got[1], got[2]}) == 3, f"keys: {got[:3]}"))
    tax = [s.get("taxonomy") for s in skillopt.parse_signals(REKEY_LOG)]
    results.append(check("skillopt: the rekey token replaces the taxonomy (rule_missing -> rule_wrong)",
                         tax[0] == "rule_wrong", f"got {tax[0]!r}"))

    print("\nD2. both checkers agree on the EFFECTIVE key (after rekey)")
    a = [s["class_key"] for s in skillopt.parse_signals(REKEY_LOG)]
    b = [s["class_key"] for s in harness.parse_signals(REKEY_LOG)]
    results.append(check("parse_signals keys identical across checkers", a == b,
                         f"skillopt={a} harness={b}"))

    failed = results.count(False)
    print(f"\n{len(results) - failed}/{len(results)} checks passed")
    return 1 if failed else 0


def test_class_key_regression():
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
