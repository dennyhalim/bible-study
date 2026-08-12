#!/usr/bin/env python3
"""Build KJV + Strong's Obsidian notes from eBible.org KJV2006 USFX.

The source archive contains several XML files. The canonical Bible text file
is explicitly selected as eng-kjv2006_usfx.xml.

For CI reliability, the source XML is intended to be committed under
vendor/kjv2006/. The downloader is only a refresh mechanism: if downloading
fails, the committed source is used automatically.

This importer never opens or writes bible_mt_tr.sqlite.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
import re

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
RAW = BUILD / "raw" / "ebible"
VAULT = BUILD / "obsidian-kjv"
VENDORED_XML = ROOT / "vendor" / "kjv2006" / "eng-kjv2006_usfx.xml"

SOURCE_PAGE = "https://ebible.org/find/show.php?id=eng-kjv2006"
SOURCE_URL = "https://ebible.org/Scriptures/eng-kjv2006_usfx.zip"
SOURCE_XML_NAME = "eng-kjv2006_usfx.xml"

BOOKS = [
    ("GEN","Genesis"),("EXO","Exodus"),("LEV","Leviticus"),("NUM","Numbers"),
    ("DEU","Deuteronomy"),("JOS","Joshua"),("JDG","Judges"),("RUT","Ruth"),
    ("1SA","1 Samuel"),("2SA","2 Samuel"),("1KI","1 Kings"),("2KI","2 Kings"),
    ("1CH","1 Chronicles"),("2CH","2 Chronicles"),("EZR","Ezra"),
    ("NEH","Nehemiah"),("EST","Esther"),("JOB","Job"),("PSA","Psalms"),
    ("PRO","Proverbs"),("ECC","Ecclesiastes"),("SNG","Song of Solomon"),
    ("ISA","Isaiah"),("JER","Jeremiah"),("LAM","Lamentations"),("EZK","Ezekiel"),
    ("DAN","Daniel"),("HOS","Hosea"),("JOL","Joel"),("AMO","Amos"),
    ("OBA","Obadiah"),("JON","Jonah"),("MIC","Micah"),("NAM","Nahum"),
    ("HAB","Habakkuk"),("ZEP","Zephaniah"),("HAG","Haggai"),
    ("ZEC","Zechariah"),("MAL","Malachi"),("MAT","Matthew"),("MRK","Mark"),
    ("LUK","Luke"),("JHN","John"),("ACT","Acts"),("ROM","Romans"),
    ("1CO","1 Corinthians"),("2CO","2 Corinthians"),("GAL","Galatians"),
    ("EPH","Ephesians"),("PHP","Philippians"),("COL","Colossians"),
    ("1TH","1 Thessalonians"),("2TH","2 Thessalonians"),("1TI","1 Timothy"),
    ("2TI","2 Timothy"),("TIT","Titus"),("PHM","Philemon"),("HEB","Hebrews"),
    ("JAS","James"),("1PE","1 Peter"),("2PE","2 Peter"),("1JN","1 John"),
    ("2JN","2 John"),("3JN","3 John"),("JUD","Jude"),("REV","Revelation"),
]
BOOK_MAP = dict(BOOKS)
BOOK_INDEX = {code: i for i, (code, _) in enumerate(BOOKS)}

def lname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def download(url: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url, headers={"User-Agent": "BibleStudy-KJV-Strong-Importer/2.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            data = response.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Download failed: {url}: {exc}") from exc
    if not data:
        raise RuntimeError(f"Empty download: {url}")
    path.write_bytes(data)

def clean_text(element: ET.Element) -> str:
    return " ".join("".join(element.itertext()).split())

def strongs_from_node(element: ET.Element) -> list[str]:
    found = []
    for node in element.iter():
        for value in node.attrib.values():
            for tag in re.findall(r"\b[GH]\d{1,5}\b", value.upper()):
                if tag not in found:
                    found.append(tag)
    return found

def word_items(verse: ET.Element) -> list[dict]:
    candidates = [
        n for n in verse.iter()
        if lname(n.tag) in {"w", "word", "zaln"}
    ]
    items = []
    for node in candidates:
        text = clean_text(node)
        if text:
            items.append({"text": text, "strongs": strongs_from_node(node)})
    if items:
        return items
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

    if len(verses) != 31102:
        raise RuntimeError(
            f"USFX validation failed: parsed {len(verses)} verses; expected 31,102"
        )
    return verses

def validate_source(path: Path) -> dict:
    verses = parse_usfx(path)
    strongs = sum(
        len(s) for v in verses.values() for w in v["words"] for s in [w["strongs"]]
    )
    return {"books": 66, "verses": len(verses), "strongs_tags": strongs}

def obtain_source(force_download: bool) -> tuple[Path, str]:
    VENDORED_XML.parent.mkdir(parents=True, exist_ok=True)

    if not force_download and VENDORED_XML.is_file() and VENDORED_XML.stat().st_size:
        try:
            validate_source(VENDORED_XML)
            print(f"Using committed source: {VENDORED_XML}")
            return VENDORED_XML, "committed"
        except Exception as exc:
            print(f"Committed source invalid; attempting refresh: {exc}")

    archive = RAW / "eng-kjv2006_usfx.zip"
    try:
        print("Downloading eBible.org KJV2006 USFX archive...")
        download(SOURCE_URL, archive)
        extract = RAW / "source"
        if extract.exists():
            shutil.rmtree(extract)
        extract.mkdir(parents=True)

        with zipfile.ZipFile(archive) as z:
            names = z.namelist()
            matches = [
                n for n in names
                if Path(n).name == SOURCE_XML_NAME
            ]
            if len(matches) != 1:
                raise RuntimeError(
                    f"Expected {SOURCE_XML_NAME} in archive; found {matches}"
                )
            z.extract(matches[0], extract)
            extracted = extract / matches[0]
            extracted.parent.mkdir(parents=True, exist_ok=True)

        validate_source(extracted)
        shutil.copy2(extracted, VENDORED_XML)
        print(f"Refreshed committed source: {VENDORED_XML}")
        return VENDORED_XML, "downloaded-and-committed"

    except Exception as exc:
        if VENDORED_XML.is_file() and VENDORED_XML.stat().st_size:
            validate_source(VENDORED_XML)
            print(f"Downloader failed; using committed source: {VENDORED_XML}")
            print(f"Download error: {exc}")
            return VENDORED_XML, "committed-fallback"
        raise RuntimeError(
            f"Could not obtain KJV source and no valid committed fallback exists: {exc}"
        ) from exc

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

Canonical source filename: `{SOURCE_XML_NAME}`.

This vault is an Obsidian reference layer only. It is separate from
`bible_mt_tr.sqlite`.

Strong's numbers are copied from the source markup and are not inferred.
""", encoding="utf-8")

    words = tags = 0

    for (code, chapter, verse_no), data in sorted(
        verses.items(), key=lambda x: (BOOK_INDEX[x[0][0]], x[0][1], x[0][2])
    ):
        book = BOOK_MAP[code]
        rendered = []
        rows = ["| # | KJV word | Strong's |", "|---:|---|---|"]
        for i, item in enumerate(data["words"], 1):
            text = item["text"]
            ids = item["strongs"]
            links = " ".join(f"[[Strong's {s}]]" for s in ids)
            rendered.append(f"**{text}** {links}".strip())
            rows.append(f"| {i} | {text} | {', '.join(ids)} |")
            words += 1
            tags += len(ids)

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

    return {"books": 66, "verses": 31102, "words": words, "strongs_tags": tags}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true",
                        help="Attempt download even when committed source exists.")
    parser.add_argument("--keep-raw", action="store_true")
    args = parser.parse_args()

    sqlite = BUILD / "bible_mt_tr.sqlite"
    if sqlite.exists():
        raise RuntimeError(
            "Refusing to run: build/bible_mt_tr.sqlite exists. "
            "KJV importer never touches the MT/TR SQLite database."
        )

    BUILD.mkdir(parents=True, exist_ok=True)
    source, acquisition = obtain_source(args.refresh)
    report = validate_source(source)
    result = generate(parse_usfx(source))

    report.update(result)
    report["source"] = {
        "provider": "eBible.org",
        "id": "eng-kjv2006",
        "edition": "KJV 1769 standardized edition",
        "source_page": SOURCE_PAGE,
        "archive": SOURCE_URL,
        "xml": SOURCE_XML_NAME,
        "xml_sha256": sha256(source),
        "xml_bytes": source.stat().st_size,
        "acquisition": acquisition,
        "vendored": str(VENDORED_XML.relative_to(ROOT)),
    }

    (BUILD / "build_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (BUILD / "source_manifest.json").write_text(
        json.dumps({
            "source": report["source"],
            "validation": {
                "books": 66,
                "verses": 31102,
            },
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    if not args.keep_raw and RAW.exists():
        shutil.rmtree(RAW)

    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
