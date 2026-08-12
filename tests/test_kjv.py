#!/usr/bin/env python3
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
report = json.loads((root/"build/build_report.json").read_text())

assert report["books"] == 66
assert report["verses"] == 31102
assert report["words"] > 0
assert report["strongs_tags"] > 0

vault = root/"build/obsidian-kjv/KJV"
assert vault.is_dir()
assert len(list(vault.rglob("*.md"))) == 31102

assert not (root/"build/bible_mt_tr.sqlite").exists()

print("PASS: CrossWire KJV / 66 books / 31,102 verses / SQLite untouched.")
