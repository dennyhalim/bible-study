#!/usr/bin/env python3
"""Build KJV + Strong's Obsidian notes from BibleEngine static JSON.

BibleEngine documents:
  /v1/kjv/manifest.json
  /v1/kjvstrongs/{BB}/{CCC}.json

This is an Obsidian-only reference layer. It never writes bible_mt_tr.sqlite.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
RAW = BUILD / "raw" / "bibleengine"
VAULT = BUILD / "obsidian-kjv"

BASE = "https://bibleengine.org/v1"
MANIFEST_URL = f"{BASE}/kjv/manifest.json"
STRONGS_URL = f"{BASE}/kjvstrongs/{{book:02d}}/{{chapter:03d}}.json"

# Optional independent audit source.
CROSSWIRE_REPO = "https://gitlab.com/crosswire-bible-society/kjv.git"

def fetch(url: str, attempts: int = 5) -> bytes:
    last = None
    for attempt in range(1, attempts + 1):
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "BibleStudy-KJVStrongImporter/3.0",
                "Accept": "application/json,text/plain,*/*",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                data = response.read()
            if not data:
                raise RuntimeError(f"empty response: {url}")
            return data
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:500]
            last = RuntimeError(f"HTTP {exc.code} for {url}: {body}")
            if exc.code == 404:
                break
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
        if attempt < attempts:
            time.sleep(min(2 ** (attempt - 1), 16))
    raise RuntimeError(f"Could not fetch {url}: {last}") from last

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def get_json(url: str, path: Path) -> object:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            path.unlink()
    data = fetch(url)
    try:
        obj = json.loads(data.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"Invalid JSON from {url}") from exc
    path.write_bytes(data)
    return obj

def parse_manifest(manifest: object) -> list[tuple[int, str, list[int]]]:
    """Normalize BibleEngine's manifest to (id, name, chapter verse counts)."""
    books = manifest.get("books") if isinstance(manifest, dict) else manifest
    if not isinstance(books, list):
        raise RuntimeError("BibleEngine manifest does not contain a books list")

    result = []
    for position, item in enumerate(books, 1):
        if not isinstance(item, dict):
            raise RuntimeError(f"Invalid manifest book {position}")

        book_id = item.get("id", item.get("book", position))
        name = item.get("name", item.get("title"))
        chapters = item.get("chapters")

        try:
            book_id = int(book_id)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"Invalid book id at position {position}") from exc

        if not name or not isinstance(chapters, list):
            raise RuntimeError(
                f"Manifest book {book_id} lacks name/chapters data"
            )

        verse_counts = []
        for chapter in chapters:
            if isinstance(chapter, dict):
                count = chapter.get("verses", chapter.get("verse_count"))
            else:
                count = chapter
            try:
                verse_counts.append(int(count))
            except (TypeError, ValueError) as exc:
                raise RuntimeError(
                    f"Invalid verse count for {name}, chapter {len(verse_counts)+1}"
                ) from exc

        result.append((book_id, str(name), verse_counts))

    if len(result) != 66:
        raise RuntimeError(f"Expected 66 books, manifest contains {len(result)}")
    return result

def validate_words(record: object, url: str, verse: str) -> list[tuple[str, list[str]]]:
    if not isinstance(record, dict):
        raise ValueError(f"{url} verse {verse}: record is not an object")
    words = record.get("w")
    if not isinstance(words, list):
        raise ValueError(f"{url} verse {verse}: missing w[]")

    result = []
    for item in words:
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError(f"{url} verse {verse}: malformed word {item!r}")
        surface, numbers = item
        if not isinstance(surface, str) or not isinstance(numbers, list):
            raise ValueError(f"{url} verse {verse}: malformed word {item!r}")

        tags = []
        for number in numbers:
            tag = str(number).upper()
            if not re.fullmatch(r"[GH][0-9]{1,5}", tag):
                raise ValueError(
                    f"{url} verse {verse}: invalid Strong's tag {tag!r}"
                )
            tags.append(tag)
        result.append((surface, tags))
    return result

def download_all(books):
    chapters = {}
    files = []

    for book_id, book, verse_counts in books:
        print(f"[{book_id:02}/66] {book}")
        for chapter, expected_verses in enumerate(verse_counts, 1):
            url = STRONGS_URL.format(book=book_id, chapter=chapter)
            path = RAW / f"{book_id:02d}" / f"{chapter:03d}.json"
            data = get_json(url, path)

            if not isinstance(data, dict):
                raise RuntimeError(f"Invalid chapter object: {url}")

            actual = len(data)
            if actual != expected_verses:
                raise RuntimeError(
                    f"{book} {chapter}: manifest says {expected_verses} "
                    f"verses, source returned {actual}"
                )

            for verse, record in data.items():
                if not str(verse).isdigit():
                    raise RuntimeError(f"{url}: invalid verse {verse!r}")
                validate_words(record, url, str(verse))

            chapters[(book_id, book, chapter)] = data
            files.append({
                "file": str(path.relative_to(BUILD)),
                "url": url,
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
                "verses": actual,
            })

    return chapters, files

def generate_vault(chapters):
    if VAULT.exists():
        shutil.rmtree(VAULT)
    (VAULT/"_meta").mkdir(parents=True)

    (VAULT/"_meta/README.md").write_text(
        """---
type: source
translation: KJV
layer: reference
---

# KJV + Strong's

Generated from the BibleEngine static KJV + Strong's JSON dataset.

- KJV is reference-only.
- This layer is not part of `bible_mt_tr.sqlite`.
- Strong's tags are copied from the source.
- The importer does not infer Strong's numbers.
- One Markdown note is generated per verse.
""", encoding="utf-8")

    verses = words = tags = 0

    for (book_id, book, chapter), data in chapters.items():
        for verse, record in sorted(data.items(), key=lambda x: int(x[0])):
            pairs = validate_words(
                record,
                STRONGS_URL.format(book=book_id, chapter=chapter),
                str(verse),
            )
            verses += 1
            words += len(pairs)
            tags += sum(len(x) for _, x in pairs)

            rendered = []
            table = ["| # | KJV word | Strong's |", "|---:|---|---|"]
            for n, (surface, codes) in enumerate(pairs, 1):
                links = " ".join(f"[[Strong's {code}]]" for code in codes)
                rendered.append(f"**{surface}** {links}".strip())
                table.append(f"| {n} | {surface} | {', '.join(codes)} |")

            note = f"""---
type: verse
translation: KJV
source: BibleEngine
book_id: {book_id}
book: {book}
chapter: {chapter}
verse: {verse}
---

# {book} {chapter}:{verse}

## KJV

{record.get("t", "")}

## KJV + Strong's

{' '.join(rendered)}

## Word table

{chr(10).join(table)}
"""
            path = VAULT/"KJV"/book/str(chapter)/f"{int(verse):03d}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(note, encoding="utf-8")

    return {"books": 66, "verses": verses, "words": words, "strongs_tags": tags}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--crosswire-audit",
        action="store_true",
        help="Reserved for a later optional CrossWire audit; primary build is independent.",
    )
    args = parser.parse_args()

    if (BUILD/"bible_mt_tr.sqlite").exists():
        raise RuntimeError(
            "Refusing to run: build/bible_mt_tr.sqlite exists. "
            "This KJV importer must never touch the MT/TR SQLite build."
        )

    manifest_path = RAW/"manifest.json"
    manifest = get_json(MANIFEST_URL, manifest_path)
    books = parse_manifest(manifest)

    chapters, files = download_all(books)
    report = generate_vault(chapters)

    if report["verses"] != 31102:
        raise RuntimeError(
            f"Expected 31,102 KJV verses, got {report['verses']}"
        )

    report["primary_source"] = {
        "name": "BibleEngine KJV + Strong's",
        "url": "https://bibleengine.org/",
        "manifest": MANIFEST_URL,
        "endpoint": STRONGS_URL,
        "verses": 31102,
        "license": "CC0 for software/data format; Bible text and Strong's public domain",
    }
    report["crosswire_audit"] = (
        "not-run" if not args.crosswire_audit
        else "not required for primary build"
    )

    (BUILD/"build_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2)+"\n",
        encoding="utf-8")
    (BUILD/"source_manifest.json").write_text(
        json.dumps({
            "primary": report["primary_source"],
            "files": files,
        }, ensure_ascii=False, indent=2)+"\n",
        encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
