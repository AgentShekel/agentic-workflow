#!/usr/bin/env bash
# Install unclebob's crapper, dryer and mutator at pinned commits into one shared venv.
# Idempotent: a second run only re-checks the pins. Prints the venv python path on stdout
# (everything else goes to stderr), so callers do:  UBPY=$(bash ~/.claude/scripts/install-quality-gates.sh)
# Used by code-writing Phase 3 structural gates (skills/code-writing/references/quality-gates.md).
# Bump a pin only after running all three gates from that reference on a small real project.
set -euo pipefail

DEST="${UB_GATES_HOME:-$HOME/.claude/tools/unclebob}"
PINS="crapper 6fd92c4c9bcc56efb64a2f8743d5a2993bcfd42d
dryer 66ff6d21a42c04afcad89c78a80066176d1294b0
mutator a5a0cb803b66e0cdb8bf471b3b08af701d424a41"

mkdir -p "$DEST"
while read -r name sha; do
  repo="$DEST/$name"
  [ -d "$repo/.git" ] || git clone -q "https://github.com/unclebob/$name.git" "$repo" >&2
  git -C "$repo" cat-file -e "$sha^{commit}" 2>/dev/null || git -C "$repo" fetch -q origin >&2
  # Editable installs run the checkout as-is, so local edits would run under a pinned name.
  if [ -n "$(git -C "$repo" status --porcelain --untracked-files=no)" ]; then
    echo "install-quality-gates: $repo has local changes; restore it (git -C \"$repo\" checkout -- .) and re-run" >&2
    exit 1
  fi
  git -C "$repo" checkout -q "$sha" >&2
done <<< "$PINS"

# The upstream ./crapper launchers hard-code .venv/bin/python and break on Windows,
# so we build our own venv and call the modules directly.
VPY="$DEST/.venv/Scripts/python.exe"
[ -x "$VPY" ] || VPY="$DEST/.venv/bin/python"
if [ ! -x "$VPY" ]; then
  BOOT=""
  for c in python python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
      BOOT="$c"; break
    fi
  done
  [ -n "$BOOT" ] || { echo "install-quality-gates: need Python >= 3.11" >&2; exit 1; }
  "$BOOT" -m venv "$DEST/.venv" >&2
  VPY="$DEST/.venv/Scripts/python.exe"
  [ -x "$VPY" ] || VPY="$DEST/.venv/bin/python"
fi
# Skip pip (and the network) when this exact pin set is already installed in this venv.
STAMP="$DEST/.venv/.installed-pins"
if [ "$(cat "$STAMP" 2>/dev/null)" != "$PINS" ]; then
  "$VPY" -m pip install -q --disable-pip-version-check -e "$DEST/crapper" -e "$DEST/dryer" -e "$DEST/mutator" >&2
  printf '%s' "$PINS" > "$STAMP"
fi
echo "$VPY"
