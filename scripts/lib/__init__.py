"""Shared library code for ~/.claude/scripts/ — single-import point for cross-
script utilities. Currently exports:

- ledger: append-only event ledger (engagement/events.jsonl); see
  scripts/lib/ledger.py for schema details.
"""
