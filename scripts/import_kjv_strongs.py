#!/usr/bin/env python3
"""Build KJV + Strong's Obsidian notes from eBible.org KJV2006 USFX.

Primary source:
  https://ebible.org/Scriptures/eng-kjv2006_usfx.zip

eBible identifies ENGKJV / eng-kjv2006 as the standardized 1769 KJV with
Strong's numbers added. The source is credited to CrossWire Bible Society.

This importer never opens or writes bible_mt_tr.sqlite.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
RAW = BUILD / "raw" / "ebible"
VAULT = BUILD / "obsidian-kjv"

SOURCE_PAGE = "https://ebible.org/find/show.php?id=eng-kjv2006"
SOURCE_URL = "https://ebible.org/Scriptures/eng-kjv2006_usfx.zip"

BOOKS = [
    ("GEN", "Genesis"), ("EXO", "Exodus"), ("LEV", "Leviticus"),
    ("NUM", "Numbers"), ("DEU", "Deuteronomy"), ("JOS", "Joshua"),
    ("JDG", "Judges"), ("RUT", "Ruth"), ("1SA", "1 Samuel"),
    ("2SA", "2 Samuel"), ("1KI", "1 Kings"), ("2KI", "2 Kings"),
    ("1CH", "1 Chronicles"), ("2CH", "2 Chronicles"), ("EZR", "Ezra"),
    ("NEH", "Nehemiah"), ("EST", "Esther"), ("JOB", "Job"),
    ("PSA", "Psalms"), ("PRO", "Proverbs"), ("ECC", "Ecclesiastes"),
    ("SNG", "Song of Solomon"), ("ISA", "Isaiah"), ("JER", "Jeremiah"),
    ("LAM", "Lamentations"), ("EZK", "Ezekiel"), ("DAN", "Daniel"),
    ("HOS", "Hosea"), ("JOL", "Joel"), ("AMO", "Amos"), ("OBA", "Obadiah"),
    ("JON", "Jonah"), ("MIC", "Micah"), ("NAM", "Nahum"),
    ("HAB", "Habakkuk"), ("ZEP", "Zephaniah"), ("HAG", "Haggai"),
    ("ZEC", "Zechariah"), ("MAL", "Malachi"), ("MAT", "Matthew"),
    ("MRK", "Mark"), ("LUK", "Luke"), ("JHN", "John"), ("ACT", "Acts"),
    ("ROM", "Romans"), ("1CO", "1 Corinthians"), ("2CO", "2 Corinthians"),
    ("GAL", "Galatians"), ("EPH", "Ephesians"), ("PHP", "Philippians"),
    ("COL", "Colossians"), ("1TH", "1 Thessalonians"),
    ("2TH", "2 Thessalonians"), ("1TI", "1 Timothy"), ("2TI", "2 Timothy"),
    ("TIT", "Titus"), ("PHM", "Philemon"), ("HEB", "Hebrews"),
    ("JAS", "James"), ("1PE", "1 Peter"), ("2PE", "2 Peter"),
    ("1JN", "1 John"), ("2JN", "2 John"), ("3JN", "3 John"),
    ("JUD", "Jude"), ("REV", "Revelation"),
]
BOOK_MAP = dict(BOOKS)

def lname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()

def download(url: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "BibleStudy-KJV-Strong-Importer/1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            data = response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"HTTP {exc.code} for {url}: {body}") from exc
    if not data:
        raise RuntimeError(f"Empty download: {url}")
    path.write_bytes(data)

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def clean_text(element: ET.Element) -> str:
    return " ".join("".join(element.itertext()).split())

def strongs_from_node(element: ET.Element) -> list[str]:
    """Collect Strong's IDs from any USFX/USFM-derived attribute.

    We intentionally inspect all attributes rather than assuming one vendor-
    specific attribute name. This handles strong="H...", lemma="strong:H...",
    x-strong="G...", and similar encodings.
    """
    found = []
    for node in element.iter():
        for value in node.attrib.values():
            for tag in re.findall(r"\b[GH]\d{1,5}\b", value.upper()):
                if tag not in found:
                    found.append(tag)
    return found

def word_items(verse: ET.Element) -> list[dict]:
    items = []

    # Preferred word-level elements.
    candidates = [
        node for node in verse.iter()
        if lname(node.tag) in {"w", "word", "zaln"}
    ]

    for node in candidates:
        text = clean_text(node)
        tags = strongs_from_node(node)
        if text:
            items.append({"text": text, "strongs": tags})

    if items:
        return items

    # Fallback: retain verse text if the source uses another USFX encoding.
    return [{"text": clean_text(verse), "strongs": strongs_from_node(verse)}]

def parse_usfx(xml_path: Path) -> dict:
    root = ET.parse(xml_path).getroot()
    verses = {}
    current_book = None
    current_chapter = None

    for node in root.iter():
        tag = lname(node.tag)

        if tag == "book":
            raw = node.attrib.get("id") or node.attrib.get("code")
            if raw:
                current_book = raw.upper().split()[0]

        elif tag in {"c", "chapter"}:
            raw = node.attrib.get("id") or node.attrib.get("number")
            if raw and str(raw).isdigit():
                current_chapter = int(raw)

        elif tag in {"v", "verse"}:
            raw = node.attrib.get("id") or node.attrib.get("number")
            if not raw or not str(raw).isdigit():
                continue
            if current_book not in BOOK_MAP or current_chapter is None:
                continue

            verse_no = int(raw)
            verses[(current_book, current_chapter, verse_no)] = {
                "text": clean_text(node),
                "words": word_items(node),
            }

    if len(verses) < 30000:
        raise RuntimeError(
            f"USFX parse produced {len(verses)} verses; expected 31,102. "
            "The source structure may have changed."
        )
    return verses

def locate_xml(directory: Path) -> Path:
    files = list(directory.rglob("*.xml"))
    if len(files) != 1:
        raise RuntimeError(
            "Expected exactly one XML file in USFX archive; found: "
            + ", ".join(str(p.relative_to(directory)) for p in files)
        )
    return files[0]

def generate(verses: dict) -> dict:
    if VAULT.exists():
        shutil.rmtree(VAULT)
    (VAULT / "_meta").mkdir(parents=True)

    (VAULT / "_meta/README.md").write_text(
        f"""---
type: source
translation: KJV
source: eBible.org
edition: eng-kjv2006
---

# KJV + Strong's

Source: [eBible.org KJV2006]({SOURCE_PAGE})

The source describes this edition as the standardized 1769 KJV, protocanon
only, with Strong's numbers added.

Strong's numbers are preserved from the source. The importer does not infer
or alter them.

This vault is an Obsidian reference layer only. It is separate from
`bible_mt_tr.sqlite`.
""", encoding="utf-8")

    count = words = tags = 0

    for (code, chapter, verse_no), data in sorted(
        verses.items(),
        key=lambda item: (
            next(i for i, (b, _) in enumerate(BOOKS) if b == item[0][0]),
            item[0][1], item[0][2],
        ),
    ):
        book = BOOK_MAP[code]
        rendered = []
        rows = ["| # | KJV word | Strong's |", "|---:|---|---|"]

        for i, item in enumerate(data["words"], 1):
            text = item["text"]
            strongs = item["strongs"]
            links = " ".join(f"[[Strong's {s}]]" for s in strongs)
            rendered.append(f"**{text}** {links}".strip())
            rows.append(f"| {i} | {text} | {', '.join(strongs)} |")
            words += 1
            tags += len(strongs)

        note = f"""---
type: verse
translation: KJV
source: eBible.org
edition: eng-kjv2006
book: {book}
chapter: {chapter}
verse: {verse_no}
---

# {book} {chapter}:{verse_no}

## KJV

{data["text"]}

## KJV + Strong's

{' '.join(rendered)}

## Word table

{chr(10).join(rows)}
"""
        path = VAULT / "KJV" / book / str(chapter) / f"{verse_no:03d}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(note, encoding="utf-8")
        count += 1

    if count != 31102:
        raise RuntimeError(f"Expected 31,102 verses, generated {count}")

    return {
        "books": 66,
        "verses": count,
        "words": words,
        "strongs_tags": tags,
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep-raw", action="store_true")
    args = parser.parse_args()

    sqlite = BUILD / "bible_mt_tr.sqlite"
    if sqlite.exists():
        raise RuntimeError(
            "Refusing to run: build/bible_mt_tr.sqlite exists. "
            "KJV importer never touches the MT/TR SQLite database."
        )

    archive = RAW / "eng-kjv2006_usfx.zip"
    extract = RAW / "source"

    if extract.exists():
        shutil.rmtree(extract)
    extract.mkdir(parents=True, exist_ok=True)

    print("Downloading eBible.org KJV2006 USFX...")
    download(SOURCE_URL, archive)

    with zipfile.ZipFile(archive) as z:
        bad = [n for n in z.namelist() if Path(n).is_absolute() or ".." in Path(n).parts]
        if bad:
            raise RuntimeError(f"Unsafe ZIP paths detected: {bad[:3]}")
        z.extractall(extract)

    xml_path = locate_xml(extract)
    print(f"Parsing USFX: {xml_path}")

    verses = parse_usfx(xml_path)
    report = generate(verses)
    report["source"] = {
        "provider": "eBible.org",
        "id": "eng-kjv2006",
        "edition": "King James Version, standardized 1769, protocanon",
        "strongs": True,
        "source_page": SOURCE_PAGE,
        "download": SOURCE_URL,
        "archive_sha256": sha256(archive),
        "archive_bytes": archive.stat().st_size,
        "xml_sha256": sha256(xml_path),
        "xml_bytes": xml_path.stat().st_size,
    }

    (BUILD / "build_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (BUILD / "source_manifest.json").write_text(
        json.dumps({
            "source": report["source"],
            "validation": {
                "expected_books": 66,
                "expected_verses": 31102,
            },
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if not args.keep_raw:
        shutil.rmtree(RAW)

    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
