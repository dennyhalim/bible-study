#!/usr/bin/env python3
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root/"vendor/kjv2006/eng-kjv2006_usfx.xml"
report = json.loads((root/"build/build_report.json").read_text(encoding="utf-8"))

assert source.is_file() and source.stat().st_size > 0
assert report["books"] == 66
assert report["verses"] == 31102
assert report["strongs_tags"] > 0
assert len(list((root/"build/obsidian-kjv/KJV").rglob("*.md"))) == 31102
assert not (root/"build/bible_mt_tr.sqlite").exists()

print("PASS: committed/fallback KJV source / 66 books / 31,102 verses / Strong's.")
