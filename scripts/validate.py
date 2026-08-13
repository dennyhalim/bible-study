#!/usr/bin/env python3
"""Validate generated Bible Study build artifacts.

Checks the current export contract:
- SQLite exists and is structurally valid.
- Obsidian contains 1189 chapter files and at least one merged Strong's file.
- NotebookLM/Gemini contains 66 book files and merged Strong's files.
- Generated files are non-empty.
"""
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
DB = BUILD / "bible_mt_tr.sqlite"
OB = BUILD / "obsidian"
NB = BUILD / "notebooklm"

EXPECTED_BOOKS = 66
EXPECTED_CHAPTERS = 1189

def require_file(path):
    if not path.is_file() or path.stat().st_size == 0:
        raise AssertionError(f"Missing or empty file: {path}")

def require_dir(path):
    if not path.is_dir():
        raise AssertionError(f"Missing directory: {path}")

def validate_sqlite():
    require_file(DB)
    con = sqlite3.connect(DB)
    try:
        result = con.execute("PRAGMA integrity_check;").fetchone()[0]
        assert result == "ok", f"SQLite integrity check failed: {result}"

        tables = {
            row[0]
            for row in con.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        required = {"book", "verse", "word"}
        missing = required - tables
        assert not missing, f"SQLite missing tables: {sorted(missing)}"

        books = con.execute("SELECT COUNT(*) FROM book").fetchone()[0]
        verses = con.execute("SELECT COUNT(*) FROM verse").fetchone()[0]
        words = con.execute("SELECT COUNT(*) FROM word").fetchone()[0]

        assert books == EXPECTED_BOOKS, (
            f"Expected {EXPECTED_BOOKS} books, found {books}"
        )
        assert verses > 0, "SQLite contains no verses"
        assert words > 0, "SQLite contains no words"

        print(
            f"[validate] SQLite OK: {books} books, "
            f"{verses} verses, {words} words"
        )
    finally:
        con.close()

def validate_markdown_tree(name, root, expected_count, subdir):
    require_dir(root)

    book_files = sorted(root.glob("*.md"))
    assert len(book_files) == expected_count, (
        f"{name}: expected {expected_count} book files, "
        f"found {len(book_files)}"
    )

    for path in book_files:
        require_file(path)

    strongs_dir = root / subdir
    require_dir(strongs_dir)

    strongs_files = sorted(strongs_dir.glob("*.md"))
    assert strongs_files, f"{name}: no Strong's export files found"

    for path in strongs_files:
        require_file(path)

    print(
        f"[validate] {name} OK: {len(book_files)} book files + "
        f"{len(strongs_files)} merged Strong's files"
    )

def validate_obsidian():
    require_dir(OB)

    kjv = OB / "KJV"
    require_dir(kjv)

    strongs = OB / "Strong's"
    require_dir(strongs)

    strongs_files = sorted(strongs.glob("*.md"))
    assert strongs_files, "Obsidian: no Strong's export files found"
    for path in strongs_files:
        require_file(path)

    chapters = sorted(kjv.rglob("*.md"))
    assert len(chapters) == EXPECTED_CHAPTERS, (
        f"Obsidian: expected {EXPECTED_CHAPTERS} chapter files, "
        f"found {len(chapters)}"
    )

    for path in chapters:
        require_file(path)

    print(
        f"[validate] Obsidian OK: {len(chapters)} chapter files + "
        f"{len(strongs_files)} merged Strong's files"
    )

def validate_notebooklm():
    validate_markdown_tree(
        "NotebookLM/Gemini",
        NB,
        EXPECTED_BOOKS,
        "Strongs",
    )

def main():
    validate_sqlite()
    validate_obsidian()
    validate_notebooklm()
    print("[validate] ALL CHECKS PASSED")

if __name__ == "__main__":
    main()
