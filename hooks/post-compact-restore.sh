#!/bin/bash
# post-compact-restore.sh — Restore feature execution context after compaction.
# Triggered by SessionStart(compact) hook.
# Reads session_id from stdin, finds checkpoint, checks if this session is the team lead.

# Guard: jq required for JSON parsing
command -v jq &>/dev/null || exit 0

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // empty')

[ -z "$CWD" ] && exit 0

# Engagement context wins over feature checkpoint.
# If an active agency engagement/ exists in CWD, suppress the checkpoint —
# its content is stale relative to ongoing engagement work, and was the
# root cause of "ignore this checkpoint" pollution after a context compact.
if [ -f "$CWD/engagement/criteria.md" ]; then
  echo "Active agency engagement detected. Read these files for engagement context:"
  echo ""
  echo "- $CWD/engagement/criteria.md"
  [ -f "$CWD/engagement/plan.md" ]            && echo "- $CWD/engagement/plan.md"
  [ -f "$CWD/engagement/validation-log.md" ]  && echo "- $CWD/engagement/validation-log.md"
  [ -f "$CWD/engagement/handoff.md" ]         && echo "- $CWD/engagement/handoff.md"
  [ -f "$CWD/engagement/acceptance-log.md" ]  && echo "- $CWD/engagement/acceptance-log.md"

  # Cross-domain secondary engagements
  if [ -d "$CWD/engagement-secondary" ]; then
    for sec in "$CWD"/engagement-secondary/*/criteria.md; do
      [ -f "$sec" ] || continue
      sec_dir=$(dirname "$sec")
      sec_domain=$(basename "$sec_dir")
      echo ""
      echo "  Secondary engagement (domain=$sec_domain):"
      echo "  - $sec"
      [ -f "$sec_dir/handoff.md" ] && echo "  - $sec_dir/handoff.md"
      [ -f "$sec_dir/acceptance-log.md" ] && echo "  - $sec_dir/acceptance-log.md"
    done
  fi

  echo ""
  echo "Feature checkpoint suppressed: engagement context takes precedence."
  exit 0
fi

# Legacy feature-execution checkpoint recovery REMOVED 2026-06-05 (Workflow
# migration). The `feature-execution` skill + its `checkpoint.yml` / `work/`
# team-lead model were archived: long agency runs now execute INSIDE the
# `engagement-workflow` Workflow, which runs out-of-band (survives a main-loop
# compaction) and resumes via `resumeFromRunId` — not a checkpoint file. The
# engagement-context branch above IS the live post-compaction restore; outside
# an active engagement there is nothing engagement-specific to recover.
exit 0
