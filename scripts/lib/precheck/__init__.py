"""Pre-handoff machine checks — modularized package.

The main entry point is `~/.claude/scripts/handoff-precheck.py` (kept as a
thin CLI/dispatcher). Each topic-area module exposes `check_*` functions with
the same signature and return-dict shape used before the modular refactor:

    {
      "name":   str,                # check identifier (kebab-case)
      "status": "pass"|"fail"|"warn"|"skip",
      "detail": str,                # short human-readable diagnosis
      "fix":    str (optional),     # remedy hint, present on fail/warn
    }

Modules:
  - common      shared constants + read_criteria_meta + subprocess runner
  - criteria    engagement structure: whitelist, criteria-frontmatter,
                preflight, size-drift, tasks-decomposition
  - handoff     handoff.md content: paths, sections, cross-val quotes,
                self-acceptance thinness, slot-language ban
  - iteration   multi-iteration discipline: iteration-counter, executor
                iteration structure, validator-output freshness,
                specialist criteria acknowledgement
  - validators  validation-outputs JSON sanity + trace-schema
  - acceptance  director-side artefacts: acceptance-log paths, canonical
                verdict, human-directive, director-verdict adjudication
  - danger      danger-scan (dangerous-ops authorization)

Re-exports below preserve the historical flat namespace so any future caller
that does `from lib.precheck import check_whitelist` keeps working without
having to know the topic split.
"""

from .common import (
    WHITELIST,
    CRITERIA_FRONTMATTER_REQUIRED,
    read_criteria_meta,
    run,
)
from .criteria import (
    check_whitelist,
    check_criteria_frontmatter,
    check_preflight,
    check_size_drift,
    check_tasks_decomposition,
)
from .handoff import (
    REQUIRED_HANDOFF_SECTIONS,
    UX_HEAVY_SECTION_6,
    SLOT_LANGUAGE_PATTERNS,
    SCANNED_FILES,
    SLOT_QUOTE_HINTS,
    check_handoff_paths,
    check_handoff_sections,
    check_cross_val_quotes,
    check_self_acceptance_thinness,
    check_slot_language,
)
from .iteration import (
    check_iteration_counter,
    check_executor_iteration_structure,
    check_validator_output_freshness,
    check_specialist_criteria_ack,
)
from .validators import (
    OPTIONAL_VALIDATORS,
    check_validator_outputs,
    check_trace_schema,
)
from .acceptance import (
    HUMAN_DIRECTIVE_DECISIONS,
    check_acceptance_log_paths,
    check_verdict_canonical,
    check_human_directive,
    check_director_verdict,
)
from .danger import check_danger_scan

__all__ = [
    # Constants
    "WHITELIST",
    "CRITERIA_FRONTMATTER_REQUIRED",
    "REQUIRED_HANDOFF_SECTIONS",
    "UX_HEAVY_SECTION_6",
    "SLOT_LANGUAGE_PATTERNS",
    "SCANNED_FILES",
    "SLOT_QUOTE_HINTS",
    "OPTIONAL_VALIDATORS",
    "HUMAN_DIRECTIVE_DECISIONS",
    # Utilities
    "read_criteria_meta",
    "run",
    # criteria.py checks
    "check_whitelist",
    "check_criteria_frontmatter",
    "check_preflight",
    "check_size_drift",
    "check_tasks_decomposition",
    # handoff.py checks
    "check_handoff_paths",
    "check_handoff_sections",
    "check_cross_val_quotes",
    "check_self_acceptance_thinness",
    "check_slot_language",
    # iteration.py checks
    "check_iteration_counter",
    "check_executor_iteration_structure",
    "check_validator_output_freshness",
    "check_specialist_criteria_ack",
    # validators.py checks
    "check_validator_outputs",
    "check_trace_schema",
    # acceptance.py checks
    "check_acceptance_log_paths",
    "check_verdict_canonical",
    "check_human_directive",
    "check_director_verdict",
    # danger.py checks
    "check_danger_scan",
]
