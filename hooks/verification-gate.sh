#!/bin/bash
# verification-gate.sh — Verification Gate before commit.
# Triggered by PreToolUse(Bash) hook (runs IN PARALLEL with pre-commit-check.sh, not after it).
# Self-gates on `git commit`. Ensures tests pass and linter is clean before commit.
# Inspired by Superpowers "proof before claims" principle.

INPUT=$(cat)
printf '%s' "$INPUT" | grep -qi 'git' || exit 0
command -v jq >/dev/null 2>&1 || exit 0
GUARD="$(dirname "$0")/git_bypass_guard.py"
CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null | tr -d '\r')
TOOL_NAME=$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null | tr -d '\r')

# Gate: only `git commit` via Bash, including `cd X && git commit` and `git -C <dir> commit`
# (git_bypass_guard.py --classify parses them; a regex on "git commit" missed `git -C x commit`).
[ "$TOOL_NAME" = "Bash" ] || exit 0
# Hooks run in parallel: a commit the bypass guard denies (pre-commit-check.sh) never runs, so
# do not spend up to 120 s of tests on it.
[ -n "$(printf '%s' "$INPUT" | python "$GUARD" 2>/dev/null)" ] && exit 0
CLASS=$(printf '%s' "$INPUT" | python "$GUARD" --classify 2>/dev/null)
[ "$(printf '%s' "$CLASS" | jq -r '.commit // false' 2>/dev/null | tr -d '\r')" = "true" ] || exit 0
[ -z "$CWD" ] && exit 0
ROOT_CWD="$CWD"
WARNINGS=""

# One pass per repository the command commits in (`git -C a commit && git -C b commit` verifies
# both; Codex review 2026-10-14), from that repository's root, where the project files live.
check_repo() {
# Detect project type and run appropriate checks
# Priority: package.json (JS/TS), pyproject.toml/requirements.txt (Python), Makefile

# ========== JavaScript/TypeScript ==========
if [ -f "package.json" ]; then
  # Check if test script exists
  HAS_TEST=$(python3 -c "import json; d=json.load(open('package.json')); print('yes' if 'test' in d.get('scripts',{}) else 'no')" 2>/dev/null)
  if [ "$HAS_TEST" = "yes" ]; then
    TEST_OUTPUT=$(npm test 2>&1)
    TEST_EXIT=$?
    if [ $TEST_EXIT -ne 0 ]; then
      WARNINGS="$WARNINGS"$'\n'"❌ Tests FAILED (npm test exit code: $TEST_EXIT)"
      WARNINGS="$WARNINGS"$'\n'"$(echo "$TEST_OUTPUT" | tail -15)"
    fi
  fi

  # Check if lint script exists
  HAS_LINT=$(python3 -c "import json; d=json.load(open('package.json')); print('yes' if 'lint' in d.get('scripts',{}) else 'no')" 2>/dev/null)
  if [ "$HAS_LINT" = "yes" ]; then
    LINT_OUTPUT=$(npm run lint 2>&1)
    LINT_EXIT=$?
    if [ $LINT_EXIT -ne 0 ]; then
      WARNINGS="$WARNINGS"$'\n'"⚠️ Linter has errors (npm run lint exit code: $LINT_EXIT)"
      WARNINGS="$WARNINGS"$'\n'"$(echo "$LINT_OUTPUT" | grep -E '(error|Error)' | head -10)"
    fi
  fi
fi

# Check frontend/ subdirectory (monorepo pattern)
if [ -f "frontend/package.json" ] && [ ! -f "package.json" ]; then
  cd frontend
  HAS_TEST=$(python3 -c "import json; d=json.load(open('package.json')); print('yes' if 'test' in d.get('scripts',{}) else 'no')" 2>/dev/null)
  if [ "$HAS_TEST" = "yes" ]; then
    TEST_OUTPUT=$(npm test 2>&1)
    TEST_EXIT=$?
    if [ $TEST_EXIT -ne 0 ]; then
      WARNINGS="$WARNINGS"$'\n'"❌ Frontend tests FAILED (exit code: $TEST_EXIT)"
      WARNINGS="$WARNINGS"$'\n'"$(echo "$TEST_OUTPUT" | tail -10)"
    fi
  fi
  cd "$CWD"
fi

# ========== Python ==========
if [ -f "pyproject.toml" ] || [ -f "requirements.txt" ] || [ -f "backend/requirements.txt" ]; then
  # Find pytest in PATH or common locations
  PYTEST_CMD=""
  if command -v pytest &>/dev/null; then
    PYTEST_CMD="pytest"
  elif [ -f ".venv/bin/pytest" ]; then
    PYTEST_CMD=".venv/bin/pytest"
  fi

  # Docker-based tests (monorepo with docker-compose)
  if [ -f "docker-compose.yml" ] || [ -f "docker-compose.yaml" ]; then
    # Check if backend service exists and is running
    BACKEND_SVC=$(docker compose ps --services 2>/dev/null | grep -E 'backend|voice-backend' | head -1)
    if [ -n "$BACKEND_SVC" ]; then
      RUNNING=$(docker compose ps "$BACKEND_SVC" --status running -q 2>/dev/null)
      if [ -n "$RUNNING" ]; then
        TEST_OUTPUT=$(docker compose exec -T "$BACKEND_SVC" python -m pytest tests/ --tb=short -q 2>&1)
        TEST_EXIT=$?
        if [ $TEST_EXIT -ne 0 ]; then
          WARNINGS="$WARNINGS"$'\n'"❌ Backend tests FAILED (docker pytest exit code: $TEST_EXIT)"
          WARNINGS="$WARNINGS"$'\n'"$(echo "$TEST_OUTPUT" | tail -15)"
        fi
      fi
    fi
  elif [ -n "$PYTEST_CMD" ]; then
    TEST_OUTPUT=$($PYTEST_CMD --tb=short -q 2>&1)
    TEST_EXIT=$?
    # exit 5 = no tests collected: nothing failed
    if [ $TEST_EXIT -ne 0 ] && [ $TEST_EXIT -ne 5 ]; then
      WARNINGS="$WARNINGS"$'\n'"❌ Python tests FAILED (pytest exit code: $TEST_EXIT)"
      WARNINGS="$WARNINGS"$'\n'"$(echo "$TEST_OUTPUT" | tail -15)"
    fi
  fi

  # Ruff linter
  if command -v ruff &>/dev/null; then
    RUFF_OUTPUT=$(ruff check . 2>&1)
    RUFF_EXIT=$?
    if [ $RUFF_EXIT -ne 0 ]; then
      WARNINGS="$WARNINGS"$'\n'"⚠️ Ruff linter errors:"
      WARNINGS="$WARNINGS"$'\n'"$(echo "$RUFF_OUTPUT" | head -10)"
    fi
  fi
fi
}

SEEN=""
while IFS= read -r dir; do
  dir=${dir%$'\r'}  # jq on Windows: CRLF
  cd "$ROOT_CWD" || exit 0
  if [ -n "$dir" ]; then cd "$dir" 2>/dev/null || continue; fi
  TOP=$(git rev-parse --show-toplevel 2>/dev/null) && cd "$TOP"
  CWD=$(pwd)
  case "$SEEN" in *"|$CWD|"*) continue ;; esac
  SEEN="$SEEN|$CWD|"
  BEFORE="$WARNINGS"
  check_repo
  if [ "$WARNINGS" != "$BEFORE" ]; then
    WARNINGS="$BEFORE"$'\n'"In ${CWD}:${WARNINGS#"$BEFORE"}"
  fi
done < <(printf '%s' "$CLASS" | jq -r '.dirs[]' 2>/dev/null)

# ========== Output ==========
# Plain stdout from a PreToolUse hook at exit 0 never reaches the model (verified live
# 2026-10-09); only hookSpecificOutput.additionalContext does.
#   Built from real newlines and passed on stdin: `%b` used to expand backslashes in test output
#   (Windows paths: `\c` truncated the report), and a long argv broke jq on Windows.
if [ -n "$WARNINGS" ]; then
  MSG="Verification Gate: issues found before commit:${WARNINGS}"$'\n'"Fix these issues before committing, or explain why they should be skipped."
  printf '%s' "${MSG:0:6000}" | jq -cRs '{hookSpecificOutput: {hookEventName: "PreToolUse", additionalContext: .}}'
fi
exit 0
