#!/usr/bin/env python3
"""Validate that the D1 SQL export is non-empty and structurally plausible."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SQL = ROOT / "build/d1/bible_mt_tr.sql"

REQUIRED = [
    "CREATE TABLE metadata",
    "CREATE TABLE book",
    "CREATE TABLE verse",
    "CREATE TABLE word",
    "CREATE TABLE translation_decision",
]

def main():
    if not SQL.is_file() or SQL.stat().st_size == 0:
        raise SystemExit("Missing or empty D1 SQL export")

    text = SQL.read_text(encoding="utf-8")

    for statement in REQUIRED:
        if statement not in text:
            raise SystemExit(f"Missing D1 statement: {statement}")

    if re.search(r"\bBEGIN\s+TRANSACTION\b", text, re.I):
        raise SystemExit("D1 SQL still contains BEGIN TRANSACTION")
    if re.search(r"^\s*COMMIT\s*;", text, re.I | re.M):
        raise SystemExit("D1 SQL still contains COMMIT")
    if re.search(r"CREATE TABLE\s+_cf_KV", text, re.I):
        raise SystemExit("D1 SQL contains reserved _cf_KV table")

    print(f"[D1] VALIDATION PASS — {SQL.stat().st_size:,} bytes")

if __name__ == "__main__":
    main()
