#!/usr/bin/env python3
from pathlib import Path
import sqlite3

root = Path(__file__).resolve().parents[1]
db = root / "build" / "bible_mt_tr.sqlite"
assert db.exists(), "SQLite database was not built"

con = sqlite3.connect(db)
assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
assert con.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 66

# KJV must never enter the canonical SQLite database.
tables = {r[0] for r in con.execute(
    "SELECT name FROM sqlite_master WHERE type='table'"
)}
assert "kjv" not in {x.lower() for x in tables}

# Required relational tables.
required = {
    "sources","books","texts","verses","lemmas","strongs","morphology",
    "lexicon_entries","words","glossary","translations",
    "translation_decisions","audits"
}
assert required.issubset(tables)

con.close()
print("Database validation passed.")
