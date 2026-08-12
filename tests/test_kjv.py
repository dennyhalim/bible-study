#!/usr/bin/env python3
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
report = json.loads(
    (root/"build/build_report.json").read_text(encoding="utf-8")
)

assert report["books"] == 66
assert report["verses"] == 31102, report
assert report["words"] > 0
assert report["strongs_tags"] > 0

vault = root/"build/obsidian-kjv/KJV"
assert vault.is_dir()

files = list(vault.rglob("*.md"))
assert len(files) == 31102, len(files)

assert not (root/"build/bible_mt_tr.sqlite").exists()

print("PASS: 66 books / 31,102 verses / KJV Obsidian-only / SQLite untouched.")
