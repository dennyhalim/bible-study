#!/usr/bin/env python3
"""Build an Obsidian KJV + Strong's layer from jsonBible.

Important:
- jsonBible book IDs are NOT zero-padded. Genesis is /1/, John is /43/.
- Chapter IDs are zero-padded to three digits, e.g. /003/.
- KJV data never enters bible_mt_tr.sqlite.
- Strong's tags are imported exactly as supplied; they are never guessed.
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
RAW = BUILD / "raw"
VAULT = BUILD / "obsidian-kjv"

BASE = "https://jsonbible.org/v1"
MANIFEST_URL = f"{BASE}/kjv/manifest.json"
STRONGS_URL = f"{BASE}/kjvstrongs/{{book_id}}/{{chapter:03d}}.json"
CROSSWIRE_RAW = (
    "https://gitlab.com/crosswire-bible-society/kjv/-/raw/master/kjv.osis.xml"
)

BOOKS = [
    "Genesis","Exodus","Leviticus","Numbers","Deuteronomy","Joshua","Judges","Ruth",
    "1 Samuel","2 Samuel","1 Kings","2 Kings","1 Chronicles","2 Chronicles","Ezra",
    "Nehemiah","Esther","Job","Psalms","Proverbs","Ecclesiastes","Song of Solomon",
    "Isaiah","Jeremiah","Lamentations","Ezekiel","Daniel","Hosea","Joel","Amos",
    "Obadiah","Jonah","Micah","Nahum","Habakkuk","Zephaniah","Haggai","Zechariah",
    "Malachi","Matthew","Mark","Luke","John","Acts","Romans","1 Corinthians",
    "2 Corinthians","Galatians","Ephesians","Philippians","Colossians",
    "1 Thessalonians","2 Thessalonians","1 Timothy","2 Timothy","Titus","Philemon",
    "Hebrews","James","1 Peter","2 Peter","1 John","2 John","3 John","Jude","Revelation"
]

def request_bytes(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "BibleMTTR-KJVImporter/1.1",
            "Accept": "application/json, application/xml, text/xml, */*",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"HTTP {exc.code} for {url}: {body}") from exc

def download(url: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(request_bytes(url))

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def safe_name(value: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", value)

def parse_manifest(data: object) -> dict[int, dict]:
    """Accept the current manifest's likely list/dict forms defensively."""
    result = {}

    def add(book_id, item):
        try:
            bid = int(book_id)
        except (TypeError, ValueError):
            return
        if not 1 <= bid <= 66:
            return
        result[bid] = item if isinstance(item, dict) else {"chapters": item}

    if isinstance(data, dict):
        # Common form: {"books": [...]}.
        books = data.get("books")
        if isinstance(books, list):
            for i, item in enumerate(books, 1):
                if isinstance(item, dict):
                    bid = item.get("id", item.get("book", i))
                    add(bid, item)
        elif isinstance(books, dict):
            for bid, item in books.items():
                add(bid, item)

        # Alternative direct numeric-keyed form.
        for key, item in data.items():
            if str(key).isdigit():
                add(key, item)

    elif isinstance(data, list):
        for i, item in enumerate(data, 1):
            add(i, item)

    if len(result) != 66:
        raise RuntimeError(
            f"Could not parse 66 books from jsonBible manifest; found {len(result)}"
        )
    return result

def chapter_numbers(book_id: int, item: dict) -> list[int]:
    value = item.get("chapters")

    if isinstance(value, int):
        return list(range(1, value + 1))

    if isinstance(value, list):
        nums = []
        for x in value:
            if isinstance(x, dict):
                x = x.get("chapter", x.get("id"))
            try:
                nums.append(int(x))
            except (TypeError, ValueError):
                pass
        if nums:
            return sorted(set(nums))

    if isinstance(value, dict):
        nums = []
        for key in value:
            try:
                nums.append(int(key))
            except ValueError:
                pass
        if nums:
            return sorted(set(nums))

    # Fallback only if the manifest does not expose chapter counts.
    known_counts = [
        50,40,27,36,34,24,21,4,31,24,22,25,29,36,10,13,10,42,150,31,12,8,66,52,
        5,48,12,14,3,9,1,4,7,3,3,3,2,14,4,28,16,24,21,28,16,16,13,6,6,4,4,5,
        3,6,4,3,13,5,5,3,5,1,1,1,22
    ]
    return list(range(1, known_counts[book_id - 1] + 1))

def extract_words(record: dict) -> list[tuple[str, list[str]]]:
    words = record.get("w")
    if not isinstance(words, list):
        raise ValueError("Verse record missing ordered 'w' array")

    result = []
    for item in words:
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError(f"Malformed tagged word: {item!r}")

        surface, tags = item
        if not isinstance(surface, str) or not isinstance(tags, list):
            raise ValueError(f"Malformed tagged word: {item!r}")

        codes = []
        for tag in tags:
            code = str(tag).upper()
            if not re.fullmatch(r"[GH]\d{1,5}", code):
                raise ValueError(f"Invalid Strong's code {code!r}")
            codes.append(code)

        result.append((surface, codes))
    return result

def build_vault(chapters: dict[tuple[int, str], dict[str, dict]]) -> dict:
    if VAULT.exists():
        shutil.rmtree(VAULT)

    (VAULT / "_meta").mkdir(parents=True)

    (VAULT / "_meta" / "README.md").write_text(
        """# KJV + Strong's

Generated from jsonBible KJV + Strong's tagged JSON.

## Role

Reference layer only.

The KJV is **not stored in `bible_mt_tr.sqlite`**.
Strong's numbers are copied from the source and are not inferred by the importer.

## Source

jsonBible KJV + Strong's:
`https://jsonbible.org/`

## File layout

`KJV/<Book>/<chapter>/<verse>.md`
""",
        encoding="utf-8",
    )

    verses = words = tags = 0

    for (book_id, book), chapter_map in chapters.items():
        for chapter, verse_map in sorted(chapter_map.items(), key=lambda x: int(x[0])):
            for verse, record in sorted(verse_map.items(), key=lambda x: int(x[0])):
                if not isinstance(record, dict):
                    raise ValueError(f"{book} {chapter}:{verse}: invalid record")

                word_list = extract_words(record)
                verses += 1
                words += len(word_list)
                tags += sum(len(codes) for _, codes in word_list)

                rendered = []
                rows = [
                    "| # | KJV word | Strong's |",
                    "|---:|---|---|",
                ]

                for pos, (surface, codes) in enumerate(word_list, 1):
                    links = " ".join(f"[[{code}]]" for code in codes)
                    rendered.append(f"**{surface}** {links}".strip())
                    rows.append(
                        f"| {pos} | {surface} | {', '.join(codes)} |"
                    )

                text = record.get("t", "")
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

{text}

## KJV + Strong's

{' '.join(rendered)}

## Word table

{chr(10).join(rows)}
"""
                path = (
                    VAULT / "KJV" / safe_name(book) / str(chapter) /
                    f"{int(verse):03}.md"
                )
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(note, encoding="utf-8")

    return {
        "books": len(chapters),
        "verses": verses,
        "words": words,
        "strongs_tags": tags,
    }

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--download-crosswire",
        action="store_true",
        help="Download CrossWire OSIS for independent audit.",
    )
    args = parser.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)

    manifest_path = RAW / "jsonbible" / "manifest.json"
    if not manifest_path.exists():
        download(MANIFEST_URL, manifest_path)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    books = parse_manifest(manifest)

    # Ensure IDs are the numeric IDs used by jsonBible:
    # Genesis=1 ... John=43 ... Revelation=66.
    for book_id, expected_name in enumerate(BOOKS, 1):
        item = books[book_id]
        actual_name = item.get("name") or item.get("title") if isinstance(item, dict) else None
        if actual_name and str(actual_name).strip().lower() != expected_name.lower():
            raise RuntimeError(
                f"Manifest book {book_id}: expected {expected_name!r}, got {actual_name!r}"
            )

    chapters = {}

    for book_id in range(1, 67):
        book = BOOKS[book_id - 1]
        for chapter in chapter_numbers(book_id, books[book_id]):
            url = STRONGS_URL.format(book_id=book_id, chapter=chapter)
            path = RAW / "jsonbible" / str(book_id) / f"{chapter:03}.json"

            if not path.exists():
                download(url, path)

            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise RuntimeError(f"Invalid JSON object: {url}")

            # Validate every verse before generating any output.
            for verse, record in data.items():
                if not str(verse).isdigit():
                    raise RuntimeError(f"Invalid verse key {verse!r} in {url}")
                extract_words(record)

            chapters[(book_id, book)] = {str(chapter): data}

    report = build_vault(chapters)

    manifest_entries = []
    for path in sorted(RAW.rglob("*")):
        if path.is_file():
            manifest_entries.append({
                "file": str(path.relative_to(BUILD)),
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
            })

    report["primary_source"] = {
        "name": "jsonBible KJV + Strong's",
        "manifest": MANIFEST_URL,
        "tagged_template": BASE + "/kjvstrongs/{book_id}/{chapter:03d}.json",
    }

    if args.download_crosswire:
        path = RAW / "crosswire" / "kjv.osis.xml"
        download(CROSSWIRE_RAW, path)
        ET.parse(path)  # Well-formedness check.
        report["crosswire"] = {
            "status": "downloaded_and_well_formed",
            "url": CROSSWIRE_RAW,
            "sha256": sha256(path),
        }

    (BUILD / "build_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    (BUILD / "source_manifest.json").write_text(
        json.dumps(
            {
                "primary": report["primary_source"],
                "secondary": report.get("crosswire"),
                "files": manifest_entries,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
