#!/usr/bin/env python3
"""Download jsonBible KJV+Strong's and generate an Obsidian reference vault.

jsonBible has no manifest.json endpoint. Use the published 66-book chapter
counts locally and fetch only real chapters.

Source format documented by jsonBible:
  /v1/kjvstrongs/{book_id}/{chapter:03d}.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
RAW = BUILD / "raw" / "jsonbible"
VAULT = BUILD / "obsidian-kjv"

BASE = "https://jsonbible.org/v1/kjvstrongs"
CROSSWIRE = "https://gitlab.com/crosswire-bible-society/kjv/-/raw/master/kjv.osis.xml"

BOOKS = [
("Genesis",50),("Exodus",40),("Leviticus",27),("Numbers",36),("Deuteronomy",34),
("Joshua",24),("Judges",21),("Ruth",4),("1 Samuel",31),("2 Samuel",24),
("1 Kings",22),("2 Kings",25),("1 Chronicles",29),("2 Chronicles",36),
("Ezra",10),("Nehemiah",13),("Esther",10),("Job",42),("Psalms",150),
("Proverbs",31),("Ecclesiastes",12),("Song of Solomon",8),("Isaiah",66),
("Jeremiah",52),("Lamentations",5),("Ezekiel",48),("Daniel",12),("Hosea",14),
("Joel",3),("Amos",9),("Obadiah",1),("Jonah",4),("Micah",7),("Nahum",3),
("Habakkuk",3),("Zephaniah",3),("Haggai",2),("Zechariah",14),("Malachi",4),
("Matthew",28),("Mark",16),("Luke",24),("John",21),("Acts",28),("Romans",16),
("1 Corinthians",16),("2 Corinthians",13),("Galatians",6),("Ephesians",6),
("Philippians",4),("Colossians",4),("1 Thessalonians",5),("2 Thessalonians",3),
("1 Timothy",6),("2 Timothy",4),("Titus",3),("Philemon",1),("Hebrews",13),
("James",5),("1 Peter",5),("2 Peter",3),("1 John",5),("2 John",1),("3 John",1),
("Jude",1),("Revelation",22)
]

def fetch(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "BibleMTTR-KJVImporter/1.2",
            "Accept": "application/json,application/xml,text/xml,*/*",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"HTTP {e.code} for {url}: {body}") from e

def download(url: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(fetch(url))

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def strongs_words(record: dict) -> list[tuple[str,list[str]]]:
    words = record.get("w")
    if not isinstance(words, list):
        raise ValueError("record has no 'w' array")
    result = []
    for item in words:
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError(f"bad word item: {item!r}")
        surface, numbers = item
        if not isinstance(surface, str) or not isinstance(numbers, list):
            raise ValueError(f"bad word item: {item!r}")
        tags = []
        for n in numbers:
            tag = str(n).upper()
            if not re.fullmatch(r"[GH]\d{1,5}", tag):
                raise ValueError(f"invalid Strong's tag: {tag}")
            tags.append(tag)
        result.append((surface, tags))
    return result

def build(chapters: dict) -> dict:
    if VAULT.exists():
        shutil.rmtree(VAULT)
    (VAULT/"_meta").mkdir(parents=True)

    (VAULT/"_meta/README.md").write_text(
        """# KJV + Strong's

KJV 1769 reference layer generated from jsonBible tagged JSON.

KJV is intentionally **not** stored in `bible_mt_tr.sqlite`.
Strong's tags are copied from the source; this importer never guesses tags.
""", encoding="utf-8")

    verses = words = tags = 0
    for (book_id, book), verse_data in chapters.items():
        for chapter, data in verse_data.items():
            for verse, record in sorted(data.items(), key=lambda x: int(x[0])):
                pairs = strongs_words(record)
                verses += 1
                words += len(pairs)
                tags += sum(len(t) for _, t in pairs)

                rendered = []
                rows = ["| # | KJV word | Strong's |", "|---:|---|---|"]
                for i, (surface, codes) in enumerate(pairs, 1):
                    links = " ".join(f"[[{c}]]" for c in codes)
                    rendered.append(f"**{surface}** {links}".strip())
                    rows.append(f"| {i} | {surface} | {', '.join(codes)} |")

                note = f"""---
type: kjv
source: jsonBible
book_id: {book_id}
book: {book}
chapter: {chapter}
verse: {verse}
sqlite_role: reference_only
---

# {book} {chapter}:{verse}

## KJV

{record.get("t","")}

## KJV + Strong's

{' '.join(rendered)}

## Word table

{chr(10).join(rows)}
"""
                path = VAULT/"KJV"/book/str(chapter)/f"{int(verse):03}.md"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(note, encoding="utf-8")

    return {"books":66, "verses":verses, "words":words, "strongs_tags":tags}

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--download-crosswire", action="store_true")
    args = ap.parse_args()

    chapters = {}
    for book_id, (book, chapter_count) in enumerate(BOOKS, 1):
        for chapter in range(1, chapter_count + 1):
            url = f"{BASE}/{book_id}/{chapter:03d}.json"
            path = RAW/str(book_id)/f"{chapter:03}.json"
            if not path.exists():
                download(url, path)
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise RuntimeError(f"Invalid JSON object: {url}")
            for verse, record in data.items():
                if not str(verse).isdigit():
                    raise RuntimeError(f"Invalid verse key in {url}: {verse!r}")
                strongs_words(record)
            chapters[(book_id, book)] = {str(chapter): data}

    report = build(chapters)
    report["primary_source"] = {
        "name": "jsonBible KJV + Strong's",
        "url": "https://jsonbible.org/",
        "tagged_endpoint": BASE + "/{book_id}/{chapter:03d}.json",
    }

    if args.download_crosswire:
        p = BUILD/"raw"/"crosswire"/"kjv.osis.xml"
        download(CROSSWIRE, p)
        ET.parse(p)
        report["crosswire"] = {
            "status":"downloaded_and_well_formed",
            "url":CROSSWIRE,
            "sha256":sha256(p),
        }

    files = []
    for p in sorted((BUILD/"raw").rglob("*")):
        if p.is_file():
            files.append({
                "file":str(p.relative_to(BUILD)),
                "sha256":sha256(p),
                "bytes":p.stat().st_size,
            })

    BUILD.mkdir(parents=True, exist_ok=True)
    (BUILD/"build_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    (BUILD/"source_manifest.json").write_text(
        json.dumps({"primary":report["primary_source"],
                    "secondary":report.get("crosswire"),
                    "files":files}, ensure_ascii=False, indent=2)+"\n",
        encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
