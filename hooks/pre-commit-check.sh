#!/bin/bash
# pre-commit-check.sh — Security scan before commit.
# Triggered by PreToolUse(Bash) hook. Self-gates on `git commit` commands.
# 1. Refuses git commands that bypass git's own hooks (git_bypass_guard.py).
# 2. On a commit, scans what is STAGED (the index, via `git grep --cached`, from the repo root,
#    in the directory the commit runs in: `cd X &&` / `git -C X`) for secret-shaped lines and
#    sensitive file names, and tells the model WHERE (file and line numbers), never WHAT:
#    the values themselves must not reach the model's context (2026-10-10 review).
#
# Output contract: plain stdout from a PreToolUse hook at exit 0 never reaches the model
# (verified live 2026-10-09); only hookSpecificOutput.additionalContext does.

INPUT=$(cat)
printf '%s' "$INPUT" | grep -qi 'git' || exit 0
GUARD="$(dirname "$0")/git_bypass_guard.py"

# The bypass guard parses the payload itself, so it still runs when jq is missing.
DENY=$(printf '%s' "$INPUT" | python "$GUARD" 2>/dev/null)
if [ -n "$DENY" ]; then
  printf '%s\n' "$DENY"
  exit 0
fi

command -v jq >/dev/null 2>&1 || exit 0
CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null | tr -d '\r')
TOOL_NAME=$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null | tr -d '\r')
[ "$TOOL_NAME" = "Bash" ] || exit 0
[ -z "$CWD" ] && exit 0

# Is this a commit, and in which directories?
CLASS=$(printf '%s' "$INPUT" | python "$GUARD" --classify 2>/dev/null)
[ "$(printf '%s' "$CLASS" | jq -r '.commit // false' 2>/dev/null | tr -d '\r')" = "true" ] || exit 0

NL=$'\n'
FINDINGS=""
SECRET_RE='(PRIVATE_KEY|SECRET_KEY|API_KEY|PASSWORD|TOKEN|aws_secret|sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{36}|glpat-[a-zA-Z0-9_-]{20}|-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY)'
SEEN=""

while IFS= read -r dir; do
  dir=${dir%$'\r'}  # jq on Windows ends lines with CRLF
  cd "$CWD" || exit 0
  if [ -n "$dir" ]; then cd "$dir" 2>/dev/null || continue; fi
  TOP=$(git rev-parse --show-toplevel 2>/dev/null) || continue
  cd "$TOP" || continue
  case "$SEEN" in *"|$TOP|"*) continue ;; esac
  SEEN="$SEEN|$TOP|"
  where=""
  [ -n "$dir" ] && where=" (in $dir)"

  # `path:line:text` from the index; -I skips binaries; lock files excluded. Only path and line
  # number are kept.
  HITS=$(git -c core.quotePath=off grep --cached -n -I -E "$SECRET_RE" -- . \
           ':(exclude)*.lock' ':(exclude)package-lock.json' ':(exclude)yarn.lock' ':(exclude)pnpm-lock.yaml' \
           2>/dev/null | cut -d: -f1,2 | head -200)
  if [ -n "$HITS" ]; then
    while IFS= read -r file; do
      [ -z "$file" ] && continue
      LINES=$(printf '%s\n' "$HITS" | awk -F: -v f="$file" '$1 == f {print $2}' | head -20 | paste -sd, -)
      FINDINGS="${FINDINGS}- possible secret in ${file}${where}, line(s) ${LINES}${NL}"
    done < <(printf '%s\n' "$HITS" | cut -d: -f1 | sort -u)
  fi

  while IFS= read -r file; do
    file=${file%$'\r'}
    case "$file" in
      .env|*/.env|.env.*|*/.env.*|*credentials.json|*secrets.json|*.key|*.pem)
        FINDINGS="${FINDINGS}- sensitive file staged: ${file}${where}${NL}" ;;
    esac
  done < <(git -c core.quotePath=off diff --cached --name-only 2>/dev/null)
done < <(printf '%s' "$CLASS" | jq -r '.dirs[]' 2>/dev/null)

if [ -n "$FINDINGS" ]; then
  MSG="Pre-commit security scan found potential issues (values not shown):${NL}${FINDINGS}Review these findings. If they are false positives, proceed with the commit."
  printf '%s' "${MSG:0:6000}" | jq -cRs '{hookSpecificOutput: {hookEventName: "PreToolUse", additionalContext: .}}'
fi
exit 0
