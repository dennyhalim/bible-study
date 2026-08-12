#!/usr/bin/env python3
"""Download, validate and convert jsonBible KJV+Strong's into Obsidian.

KJV is intentionally NOT written to bible_mt_tr.sqlite.
Primary source: jsonBible's public KJV+Strong's JSON.
Optional independent audit: CrossWire KJV OSIS.

The importer never guesses Strong's numbers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
RAW = BUILD / "raw"
VAULT = BUILD / "obsidian-kjv"

JSONBIBLE_BASE = "https://jsonbible.org/v1/kjvstrongs"
CROSSWIRE_RAW = (
    "https://gitlab.com/crosswire-bible-society/kjv/-/raw/master/kjv.osis.xml"
)

BOOKS = [
    ("01", "Genesis"), ("02", "Exodus"), ("03", "Leviticus"), ("04", "Numbers"),
    ("05", "Deuteronomy"), ("06", "Joshua"), ("07", "Judges"), ("08", "Ruth"),
    ("09", "1 Samuel"), ("10", "2 Samuel"), ("11", "1 Kings"), ("12", "2 Kings"),
    ("13", "1 Chronicles"), ("14", "2 Chronicles"), ("15", "Ezra"), ("16", "Nehemiah"),
    ("17", "Esther"), ("18", "Job"), ("19", "Psalms"), ("20", "Proverbs"),
    ("21", "Ecclesiastes"), ("22", "Song of Solomon"), ("23", "Isaiah"),
    ("24", "Jeremiah"), ("25", "Lamentations"), ("26", "Ezekiel"), ("27", "Daniel"),
    ("28", "Hosea"), ("29", "Joel"), ("30", "Amos"), ("31", "Obadiah"),
    ("32", "Jonah"), ("33", "Micah"), ("34", "Nahum"), ("35", "Habakkuk"),
    ("36", "Zephaniah"), ("37", "Haggai"), ("38", "Zechariah"), ("39", "Malachi"),
    ("40", "Matthew"), ("41", "Mark"), ("42", "Luke"), ("43", "John"),
    ("44", "Acts"), ("45", "Romans"), ("46", "1 Corinthians"),
    ("47", "2 Corinthians"), ("48", "Galatians"), ("49", "Ephesians"),
    ("50", "Philippians"), ("51", "Colossians"), ("52", "1 Thessalonians"),
    ("53", "2 Thessalonians"), ("54", "1 Timothy"), ("55", "2 Timothy"),
    ("56", "Titus"), ("57", "Philemon"), ("58", "Hebrews"), ("59", "James"),
    ("60", "1 Peter"), ("61", "2 Peter"), ("62", "1 John"), ("63", "2 John"),
    ("64", "3 John"), ("65", "Jude"), ("66", "Revelation"),
]

def get(url: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url, headers={"User-Agent": "BibleMTTR-KJVImporter/1.0"}
    )
    with urllib.request.urlopen(req, timeout=120) as src, path.open("wb") as dst:
        shutil.copyfileobj(src, dst)

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def clean_name(value: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", value)

def extract_words(record):
    """Return [(surface, [Strong codes])] from a jsonBible verse record."""
    words = record.get("w")
    if not isinstance(words, list):
        raise ValueError("Verse record has no ordered 'w' array")

    out = []
    for item in words:
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError(f"Malformed tagged word: {item!r}")
        surface, numbers = item
        if not isinstance(surface, str) or not isinstance(numbers, list):
            raise ValueError(f"Malformed word payload: {item!r}")
        codes = []
        for n in numbers:
            code = str(n).upper()
            if not re.fullmatch(r"[GH]\d{1,5}", code):
                raise ValueError(f"Invalid Strong's code: {code}")
            codes.append(code)
        out.append((surface, codes))
    return out

def load_json(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Expected chapter JSON object")
    return data

def build_vault(chapters: dict):
    if VAULT.exists():
        shutil.rmtree(VAULT)

    (VAULT / "_meta").mkdir(parents=True)
    (VAULT / "KJV").mkdir()

    (VAULT / "_meta" / "README.md").write_text(
        """# KJV + Strong's

Generated from jsonBible's `kjvstrongs` tagged JSON.

## Role

Reference layer only. KJV is **not imported into the canonical MT/TR SQLite
database**.

Each word retains the Strong's numbers supplied by the source. The importer
does not infer or rewrite Strong's tagging.

## Source

jsonBible — KJV 1769 + Strong's.
""",
        encoding="utf-8",
    )

    total_verses = total_words = total_tags = 0

    for (book_no, book), chapter_data in chapters.items():
        book_dir = VAULT / "KJV" / book
        for chapter, verses in sorted(chapter_data.items(), key=lambda x: int(x[0])):
            for verse, record in sorted(verses.items(), key=lambda x: int(x[0])):
                words = extract_words(record)
                total_verses += 1
                total_words += len(words)
                total_tags += sum(len(x[1]) for x in words)

                rendered = []
                for surface, codes in words:
                    if codes:
                        links = " ".join(f"[[{c}]]" for c in codes)
                        rendered.append(f"**{surface}** {links}")
                    else:
                        rendered.append(surface)

                rows = [
                    "| # | KJV word | Strong's |",
                    "|---:|---|---|",
                ]
                for i, (surface, codes) in enumerate(words, 1):
                    rows.append(
                        f"| {i} | {surface} | "
                        + ", ".join(f"[[{c}]]" for c in codes)
                        + " |"
                    )

                text = record.get("t", "")
                note = f"""---
type: kjv
source: jsonBible
book: {book}
chapter: {chapter}
verse: {verse}
sqlite_role: reference_only
---

# {book} {chapter}:{verse}

## KJV

{text}

## KJV + Strong's

{' '.join(rendered)}

## Word table

{chr(10).join(rows)}
"""
                path = book_dir / f"{int(verse):03}.md"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(note, encoding="utf-8")

    return {
        "verses": total_verses,
        "words": total_words,
        "strongs_tags": total_tags,
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--download-crosswire", action="store_true")
    args = ap.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    chapters = {}

    for book_no, book in BOOKS:
        for chapter in range(1, 151):
            # jsonBible returns 404 when the chapter does not exist.
            # Stop after the first missing chapter for each book.
            path = RAW / "jsonbible" / book_no / f"{chapter:03}.json"
            url = f"{JSONBIBLE_BASE}/{book_no}/{chapter:03}.json"
            try:
                if not path.exists():
                    get(url, path)
                data = load_json(path)
            except Exception:
                if chapter == 1:
                    raise RuntimeError(f"Could not fetch {url}")
                break
            chapters.setdefault((book_no, book), {})[str(chapter)] = data

    report = build_vault(chapters)

    manifest = []
    for p in sorted(RAW.rglob("*")):
        if p.is_file():
            manifest.append({
                "file": str(p.relative_to(BUILD)),
                "sha256": sha256(p),
                "bytes": p.stat().st_size,
            })

    if args.download_crosswire:
        cw = RAW / "crosswire" / "kjv.osis.xml"
        get(CROSSWIRE_RAW, cw)
        # Parse enough to ensure it is well-formed XML.
        ET.parse(cw)
        manifest.append({
            "file": str(cw.relative_to(BUILD)),
            "sha256": sha256(cw),
            "bytes": cw.stat().st_size,
        })
        report["crosswire_xml"] = "downloaded_and_well_formed"

    (BUILD / "source_manifest.json").write_text(
        json.dumps({
            "primary": {
                "name": "jsonBible KJV+Strong's",
                "base_url": JSONBIBLE_BASE,
                "role": "primary KJV+Strong's Obsidian source",
            },
            "secondary": {
                "name": "CrossWire KJV OSIS",
                "url": CROSSWIRE_RAW,
                "role": "independent audit source",
            },
            "files": manifest,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    (BUILD / "build_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
