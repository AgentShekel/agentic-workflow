#!/bin/bash
# session-start-project.sh — Auto-load project knowledge on session start.
# Triggered by SessionStart hook (non-compact sessions).
# Checks if CWD has project-knowledge and outputs context summary.

INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)

[ -z "$CWD" ] && exit 0

# Engagement context — highest priority. If an active engagement is in CWD,
# surface it first so leads/directors don't pick up stale feature checkpoints.
if [ -f "$CWD/engagement/criteria.md" ]; then
  echo "Active agency engagement detected. Read these files for engagement context:"
  echo ""
  echo "- $CWD/engagement/criteria.md"
  [ -f "$CWD/engagement/plan.md" ]            && echo "- $CWD/engagement/plan.md"
  [ -f "$CWD/engagement/validation-log.md" ]  && echo "- $CWD/engagement/validation-log.md"
  [ -f "$CWD/engagement/handoff.md" ]         && echo "- $CWD/engagement/handoff.md"
  [ -f "$CWD/engagement/acceptance-log.md" ]  && echo "- $CWD/engagement/acceptance-log.md"

  # Cross-domain secondary engagements (per engagement-protocol)
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
  echo "Engagement is the active context. Closed-feature work/ checkpoints (if any) are stale; ignore them."
  echo ""
fi

PK_DIR="$CWD/.claude/skills/project-knowledge/references"
[ -d "$PK_DIR" ] || exit 0

# Check if at least one PK file exists
PK_FILES=$(find "$PK_DIR" -name "*.md" -maxdepth 1 2>/dev/null | head -5)
[ -z "$PK_FILES" ] && exit 0

echo "Project knowledge detected. Read these files for project context:"
echo ""

for f in $PK_FILES; do
  BASENAME=$(basename "$f")
  echo "- $PK_DIR/$BASENAME"
done

# Check for active feature work
if [ -d "$CWD/work" ]; then
  ACTIVE_FEATURES=""
  for dir in "$CWD"/work/*/; do
    case "$dir" in
      "$CWD"/work/completed/*) continue ;;
    esac
    [ -f "${dir}tech-spec.md" ] && ACTIVE_FEATURES="$ACTIVE_FEATURES  - $(basename "$dir")\n"
  done
  if [ -n "$ACTIVE_FEATURES" ]; then
    echo ""
    echo "Active features in work/:"
    echo -e "$ACTIVE_FEATURES"
  fi
fi
