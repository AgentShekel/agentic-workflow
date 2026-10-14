#!/bin/bash
# lint-on-edit.sh — PostToolUse(Edit|Write) entry point registered in settings.json.
# The logic lives in lint_on_edit.py: full autofix for files the tool created,
# fixes confined to the lines the edit wrote for everything else.
exec python3 "$(dirname "$0")/lint_on_edit.py"
