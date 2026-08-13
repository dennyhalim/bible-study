#!/usr/bin/env python3
"""Convert the validated SQLite corpus into D1-compatible SQL.

Cloudflare D1 imports SQLite SQL dumps through Wrangler. The raw .sqlite file
must first be converted to SQL; transaction wrappers are removed because D1
handles the import transaction itself.
"""
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "build/bible_mt_tr.sqlite"
OUT = ROOT / "build/d1/bible_mt_tr.sql"

def main():
    if not DB.is_file():
        raise SystemExit(f"Missing database: {DB}")

    check = sqlite3.connect(DB)
    if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise SystemExit("SQLite integrity check failed")
    check.close()

    sqlite3_bin = shutil.which("sqlite3")
    if not sqlite3_bin:
        raise SystemExit("sqlite3 CLI is required")

    OUT.parent.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        [sqlite3_bin, str(DB), ".dump"],
        check=True,
        capture_output=True,
        text=True,
    )
    sql = result.stdout

    # D1 does not need the source database transaction wrapper.
    sql = re.sub(r"(?im)^\s*BEGIN TRANSACTION;\s*$", "", sql)
    sql = re.sub(r"(?im)^\s*COMMIT;\s*$", "", sql)

    # D1 owns this internal table; never import a source copy.
    sql = re.sub(
        r"(?ims)^\s*CREATE TABLE _cf_KV\b.*?;\s*",
        "",
        sql,
    )

    # sqlite3 .dump can include internal sequence/index statements that are
    # harmless locally but should not be imported from a generated database.
    sql = re.sub(
        r"(?im)^\s*DELETE FROM sqlite_sequence;\s*$",
        "",
        sql,
    )

    # Keep D1 import deterministic and explicit.
    header = """-- Generated from build/bible_mt_tr.sqlite
-- Do not edit manually.
-- Import with: npx wrangler d1 execute <DB> --remote --file=build/d1/bible_mt_tr.sql

PRAGMA foreign_keys=OFF;
"""
    OUT.write_text(header + "\n" + sql.strip() + "\n", encoding="utf-8")

    print(f"[D1] Generated {OUT}")
    print(f"[D1] Size: {OUT.stat().st_size:,} bytes")

if __name__ == "__main__":
    main()
