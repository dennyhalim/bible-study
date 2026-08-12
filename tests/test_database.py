#!/usr/bin/env python3
from pathlib import Path
import sqlite3

root = Path(__file__).resolve().parents[1]
db = root / "build" / "bible_mt_tr.sqlite"

assert db.exists(), "SQLite database was not built"

con = sqlite3.connect(db)
assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
assert con.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 66

tables = {
    row[0] for row in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
}
required = {
    "sources", "books", "texts", "verses", "lemmas", "strongs",
    "morphology", "lexicon_entries", "words", "glossary",
    "translations", "translation_decisions", "audits"
}
assert required <= tables

# KJV must not be represented as a SQLite table.
assert not any("kjv" in name.lower() for name in tables)

# The source manifest is a required build output.
manifest = root / "build" / "source_manifest.json"
assert manifest.exists() and manifest.stat().st_size > 0

con.close()
print("Database validation passed.")
