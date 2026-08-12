#!/usr/bin/env python3
"""Build the KJV + Strong's Obsidian reference layer.

Primary source: jsonBible KJV + Strong's tagged chapter JSON.
CrossWire is optional and is audit-only. A CrossWire failure never invalidates
the primary KJV build.

The generated KJV layer is deliberately separate from bible_mt_tr.sqlite.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
RAW = BUILD / "raw" / "jsonbible"
VAULT = BUILD / "obsidian-kjv"

JSONBIBLE_BASE = "https://jsonbible.org/v1/kjvstrongs"
CROSSWIRE_REPO = "https://gitlab.com/crosswire-bible-society/kjv.git"

# jsonBible documents 31,102 KJV verses and the tagged endpoint:
# /v1/kjvstrongs/{book_id}/{chapter:03d}.json
BOOKS = [
    ("Genesis", 50), ("Exodus", 40), ("Leviticus", 27), ("Numbers", 36),
    ("Deuteronomy", 34), ("Joshua", 24), ("Judges", 21), ("Ruth", 4),
    ("1 Samuel", 31), ("2 Samuel", 24), ("1 Kings", 22), ("2 Kings", 25),
    ("1 Chronicles", 29), ("2 Chronicles", 36), ("Ezra", 10), ("Nehemiah", 13),
    ("Esther", 10), ("Job", 42), ("Psalms", 150), ("Proverbs", 31),
    ("Ecclesiastes", 12), ("Song of Solomon", 8), ("Isaiah", 66),
    ("Jeremiah", 52), ("Lamentations", 5), ("Ezekiel", 48), ("Daniel", 12),
    ("Hosea", 14), ("Joel", 3), ("Amos", 9), ("Obadiah", 1), ("Jonah", 4),
    ("Micah", 7), ("Nahum", 3), ("Habakkuk", 3), ("Zephaniah", 3),
    ("Haggai", 2), ("Zechariah", 14), ("Malachi", 4), ("Matthew", 28),
    ("Mark", 16), ("Luke", 24), ("John", 21), ("Acts", 28), ("Romans", 16),
    ("1 Corinthians", 16), ("2 Corinthians", 13), ("Galatians", 6),
    ("Ephesians", 6), ("Philippians", 4), ("Colossians", 4),
    ("1 Thessalonians", 5), ("2 Thessalonians", 3), ("1 Timothy", 6),
    ("2 Timothy", 4), ("Titus", 3), ("Philemon", 1), ("Hebrews", 13),
    ("James", 5), ("1 Peter", 5), ("2 Peter", 3), ("1 John", 5),
    ("2 John", 1), ("3 John", 1), ("Jude", 1), ("Revelation", 22),
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url: str, attempts: int = 5) -> bytes:
    last: Exception | None = None

    for attempt in range(1, attempts + 1):
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "BibleStudy-KJVStrongImporter/2.0",
                "Accept": "application/json,text/plain,*/*",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                data = response.read()

            if not data:
                raise RuntimeError(f"Empty response: {url}")

            return data

        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:500]
            last = RuntimeError(
                f"HTTP {exc.code} for {url}: {body}"
            )
            # A 404 is deterministic; retrying it only wastes the run.
            if exc.code == 404:
                break

        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc

        if attempt < attempts:
            time.sleep(min(2 ** (attempt - 1), 16))

    raise RuntimeError(f"Could not fetch {url}: {last}") from last


def download_json(url: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    # Never accept an existing HTML/error page as JSON.
    if path.exists() and path.stat().st_size:
        try:
            json.loads(path.read_text(encoding="utf-8"))
            return
        except (json.JSONDecodeError, UnicodeDecodeError):
            path.unlink()

    data = fetch(url)
    try:
        json.loads(data.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"Invalid JSON from {url}") from exc

    path.write_bytes(data)


def validate_record(record: object, url: str, verse: str) -> list[tuple[str, list[str]]]:
    if not isinstance(record, dict):
        raise ValueError(f"{url} verse {verse}: record is not an object")

    words = record.get("w")
    if not isinstance(words, list):
        raise ValueError(f"{url} verse {verse}: missing w[]")

    result: list[tuple[str, list[str]]] = []

    for item in words:
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError(f"{url} verse {verse}: malformed word {item!r}")

        surface, numbers = item
        if not isinstance(surface, str) or not isinstance(numbers, list):
            raise ValueError(f"{url} verse {verse}: malformed word {item!r}")

        tags: list[str] = []
        for number in numbers:
            tag = str(number).upper()
            if not re.fullmatch(r"[GH][0-9]{1,5}", tag):
                raise ValueError(
                    f"{url} verse {verse}: invalid Strong's tag {tag!r}"
                )
            tags.append(tag)

        result.append((surface, tags))

    return result


def download_all() -> tuple[dict, dict]:
    chapters: dict = {}
    source_files: list[dict] = []

    for book_id, (book, chapter_count) in enumerate(BOOKS, 1):
        print(f"[{book_id:02}/66] {book}")

        for chapter in range(1, chapter_count + 1):
            url = f"{JSONBIBLE_BASE}/{book_id}/{chapter:03d}.json"
            path = RAW / str(book_id) / f"{chapter:03d}.json"

            download_json(url, path)
            data = json.loads(path.read_text(encoding="utf-8"))

            for verse, record in data.items():
                if not str(verse).isdigit():
                    raise ValueError(f"{url}: invalid verse key {verse!r}")
                validate_record(record, url, str(verse))

            chapters[(book_id, book, chapter)] = data
            source_files.append({
                "file": str(path.relative_to(BUILD)),
                "url": url,
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
            })

    return chapters, {"files": source_files}


def generate_vault(chapters: dict) -> dict:
    if VAULT.exists():
        shutil.rmtree(VAULT)

    (VAULT / "_meta").mkdir(parents=True)

    (VAULT / "_meta" / "README.md").write_text(
        """---
type: source
source: jsonBible
translation: KJV
layer: reference
---

# KJV + Strong's

This is a reference-only KJV + Strong's layer.

- Source: jsonBible KJV + Strong's tagged JSON
- KJV is **not** imported into `bible_mt_tr.sqlite`.
- Strong's numbers are copied from the source.
- The importer does not infer or correct Strong's numbers.
- One Markdown note is generated per verse.

## Source format

Each verse is `{t, w}`:

- `t` = KJV reading text
- `w` = ordered `[word, [Strong's numbers]]` records
""",
        encoding="utf-8",
    )

    verses = words = tags = 0

    for (book_id, book, chapter), data in chapters.items():
        for verse, record in sorted(data.items(), key=lambda x: int(x[0])):
            pairs = validate_record(
                record,
                f"{JSONBIBLE_BASE}/{book_id}/{chapter:03d}.json",
                str(verse),
            )

            verses += 1
            words += len(pairs)
            tags += sum(len(codes) for _, codes in pairs)

            rendered = []
            table = [
                "| # | KJV word | Strong's |",
                "|---:|---|---|",
            ]

            for position, (surface, codes) in enumerate(pairs, 1):
                links = " ".join(f"[[Strong's {code}]]" for code in codes)
                rendered.append(f"**{surface}** {links}".strip())
                table.append(
                    f"| {position} | {surface} | {', '.join(codes)} |"
                )

            text = record.get("t", "")

            note = f"""---
type: verse
translation: KJV
source: jsonBible
book_id: {book_id}
book: {book}
chapter: {chapter}
verse: {verse}
---

# {book} {chapter}:{verse}

## KJV

{text}

## KJV + Strong's

{' '.join(rendered)}

## Word table

{chr(10).join(table)}
"""

            path = (
                VAULT / "KJV" / book / str(chapter) /
                f"{int(verse):03d}.md"
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(note, encoding="utf-8")

    return {
        "books": 66,
        "verses": verses,
        "words": words,
        "strongs_tags": tags,
    }


def crosswire_audit() -> dict:
    """Optional audit. Failure is recorded, not fatal to the primary build."""

    audit_dir = BUILD / "raw" / "crosswire"
    audit_dir.mkdir(parents=True, exist_ok=True)
    repo_dir = audit_dir / "repo"

    if repo_dir.exists():
        shutil.rmtree(repo_dir)

    command = [
        "git", "clone",
        "--depth", "1",
        "--filter=blob:none",
        "--sparse",
        CROSSWIRE_REPO,
        str(repo_dir),
    ]

    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        subprocess.run(
            ["git", "-C", str(repo_dir), "sparse-checkout", "set", "kjv.osis.xml"],
            check=True,
            capture_output=True,
            text=True,
        )

        source = repo_dir / "kjv.osis.xml"
        if not source.exists() or not source.stat().st_size:
            raise RuntimeError("CrossWire kjv.osis.xml was not obtained")

        ET.parse(source)

        target = audit_dir / "kjv.osis.xml"
        shutil.copy2(source, target)

        return {
            "status": "ok",
            "repository": CROSSWIRE_REPO,
            "file": str(target.relative_to(BUILD)),
            "sha256": sha256(target),
            "bytes": target.stat().st_size,
        }

    except Exception as exc:
        if repo_dir.exists():
            shutil.rmtree(repo_dir, ignore_errors=True)

        return {
            "status": "unavailable",
            "repository": CROSSWIRE_REPO,
            "error": str(exc),
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--crosswire-audit",
        action="store_true",
        help="Attempt an independent CrossWire audit; failure is non-fatal.",
    )
    args = parser.parse_args()

    if (BUILD / "bible_mt_tr.sqlite").exists():
        raise RuntimeError(
            "Refusing to run: build/bible_mt_tr.sqlite exists. "
            "KJV importer must never modify the MT/TR SQLite build."
        )

    BUILD.mkdir(parents=True, exist_ok=True)

    chapters, source_manifest = download_all()
    report = generate_vault(chapters)

    expected_verses = 31102
    if report["verses"] != expected_verses:
        raise RuntimeError(
            f"Verse count mismatch: expected {expected_verses}, "
            f"got {report['verses']}"
        )

    report["primary_source"] = {
        "name": "jsonBible KJV + Strong's",
        "url": "https://jsonbible.org/",
        "endpoint": JSONBIBLE_BASE + "/{book_id}/{chapter:03d}.json",
        "verses": expected_verses,
    }

    if args.crosswire_audit:
        report["crosswire_audit"] = crosswire_audit()

    source_manifest["primary"] = report["primary_source"]
    source_manifest["crosswire_audit"] = report.get("crosswire_audit")

    (BUILD / "build_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (BUILD / "source_manifest.json").write_text(
        json.dumps(source_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
