#!/usr/bin/env python3
"""Validate the generated database before promotion."""
from pathlib import Path
import json, sqlite3

ROOT=Path(__file__).resolve().parents[1]
DB=ROOT/"build/bible_mt_tr.sqlite"
con=sqlite3.connect(DB)
assert con.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
assert con.execute("SELECT COUNT(*) FROM book").fetchone()[0]==66
assert con.execute("SELECT COUNT(*) FROM verse").fetchone()[0]==31102
assert con.execute("SELECT COUNT(*) FROM word").fetchone()[0]>0
assert con.execute(
    "SELECT COUNT(*) FROM word WHERE json_array_length(strongs_json)>0"
).fetchone()[0]>0
con.close()
print("VALIDATION PASS")
