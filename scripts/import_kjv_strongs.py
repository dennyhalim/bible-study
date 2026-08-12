#!/usr/bin/env python3
"""Build KJV + Strong's Obsidian notes from the official CrossWire KJV SWORD module.

The importer downloads the module archive from CrossWire, extracts its OSIS
source, parses embedded Strong's/morphology markup, and creates one Markdown
note per verse.

KJV remains Obsidian-only; bible_mt_tr.sqlite is never created or modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
RAW = BUILD / "raw" / "crosswire"
VAULT = BUILD / "obsidian-kjv"

# CrossWire's official current KJV module page identifies KJV 3.1.
# The module repository is the authoritative distribution source.
MODULE_URL = "https://ftp.crosswire.org/sword/packages/rawzip/KJV.zip"
MODULE_INFO = "https://www.crosswire.org/sword/modules/ModInfo.jsp?modName=KJV"

BOOKS = [
    "Gen","Exod","Lev","Num","Deut","Josh","Judg","Ruth",
    "1Sam","2Sam","1Kgs","2Kgs","1Chr","2Chr","Ezra","Neh",
    "Esth","Job","Ps","Prov","Eccl","Song","Isa","Jer","Lam",
    "Ezek","Dan","Hos","Joel","Amos","Obad","Jonah","Mic",
    "Nah","Hab","Zeph","Hag","Zech","Mal","Matt","Mark","Luke",
    "John","Acts","Rom","1Cor","2Cor","Gal","Eph","Phil","Col",
    "1Thess","2Thess","1Tim","2Tim","Titus","Phlm","Heb","Jas",
    "1Pet","2Pet","1John","2John","3John","Jude","Rev"
]
BOOK_NAMES = [
    "Genesis","Exodus","Leviticus","Numbers","Deuteronomy","Joshua","Judges","Ruth",
    "1 Samuel","2 Samuel","1 Kings","2 Kings","1 Chronicles","2 Chronicles","Ezra","Nehemiah",
    "Esther","Job","Psalms","Proverbs","Ecclesiastes","Song of Solomon","Isaiah","Jeremiah",
    "Lamentations","Ezekiel","Daniel","Hosea","Joel","Amos","Obadiah","Jonah","Micah","Nahum",
    "Habakkuk","Zephaniah","Haggai","Zechariah","Malachi","Matthew","Mark","Luke","John","Acts",
    "Romans","1 Corinthians","2 Corinthians","Galatians","Ephesians","Philippians","Colossians",
    "1 Thessalonians","2 Thessalonians","1 Timothy","2 Timothy","Titus","Philemon","Hebrews",
    "James","1 Peter","2 Peter","1 John","2 John","3 John","Jude","Revelation"
]
BOOK_MAP = dict(zip(BOOKS, BOOK_NAMES))

NS = {"osis": "http://www.bibletechnologies.net/2003/OSIS/namespace"}

def download(url: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "BibleStudy-CrossWire-KJV-Importer/1.0"}
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        data = r.read()
    if not data:
        raise RuntimeError(f"Empty download: {url}")
    path.write_bytes(data)

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]

def strong_tags(element: ET.Element) -> list[str]:
    values = []
    for node in element.iter():
        for key, value in node.attrib.items():
            if local_name(key).lower() in {"lemma", "strong"}:
                for match in re.findall(r"[GH]\d{1,5}", value.upper()):
                    if match not in values:
                        values.append(match)
    return values

def morphology(element: ET.Element) -> list[str]:
    values = []
    for node in element.iter():
        for key, value in node.attrib.items():
            if local_name(key).lower() in {"morph", "morphology"}:
                if value not in values:
                    values.append(value)
    return values

def flatten_text(element: ET.Element) -> str:
    return " ".join("".join(element.itertext()).split())

def find_osis_xml(extract_dir: Path) -> Path:
    candidates = list(extract_dir.rglob("*.xml"))
    preferred = [
        p for p in candidates
        if p.name.lower() in {"kjv.xml", "kjvfull.xml", "kjv-osis.xml"}
    ]
    if preferred:
        return preferred[0]
    if len(candidates) == 1:
        return candidates[0]
    raise RuntimeError(
        "Could not uniquely identify CrossWire OSIS/XML source in module: "
        + ", ".join(str(p.relative_to(extract_dir)) for p in candidates)
    )

def parse_osis(xml_path: Path) -> dict:
    tree = ET.parse(xml_path)
    root = tree.getroot()
    verses = {}

    for verse in root.iter():
        if local_name(verse.tag) != "verse":
            continue

        osis_id = verse.attrib.get("osisID") or verse.attrib.get("osisRef")
        if not osis_id:
            continue

        # CrossWire uses IDs such as Gen.1.1. Ignore notes and non-canonical
        # references by requiring book.chapter.verse.
        m = re.fullmatch(r"([^.]+)\.(\d+)\.(\d+)", osis_id.split()[0])
        if not m:
            continue

        book_code, chapter, verse_no = m.groups()
        if book_code not in BOOK_MAP:
            continue

        words = []
        for node in verse.iter():
            if local_name(node.tag) not in {"w", "seg"}:
                continue
            text = flatten_text(node)
            if not text:
                continue
            tags = strong_tags(node)
            morph = morphology(node)
            words.append({
                "text": text,
                "strongs": tags,
                "morphology": morph,
            })

        text = flatten_text(verse)
        verses[(book_code, int(chapter), int(verse_no))] = {
            "osis": osis_id,
            "text": text,
            "words": words,
        }

    if len(verses) < 30000:
        raise RuntimeError(
            f"OSIS parse produced only {len(verses)} verses; expected ~31,102"
        )
    return verses

def generate(verses: dict) -> dict:
    if VAULT.exists():
        shutil.rmtree(VAULT)
    (VAULT/"_meta").mkdir(parents=True)

    (VAULT/"_meta/README.md").write_text(
        """---
type: source
translation: KJV
source: CrossWire KJV SWORD module
---

# KJV + Strong's

Source: CrossWire KJV SWORD module.

The CrossWire KJV module is the KJV 1769 with embedded Strong's numbers,
morphology, and catchwords. Strong's tags are preserved as source data and
are not inferred by this importer.

This layer is **Obsidian-only** and is never stored in `bible_mt_tr.sqlite`.
""", encoding="utf-8")

    count = words = tags = morphs = 0

    for (code, chapter, verse_no), data in sorted(
        verses.items(), key=lambda x: (
            BOOKS.index(x[0][0]), x[0][1], x[0][2]
        )
    ):
        book = BOOK_MAP[code]
        rows = ["| # | KJV word | Strong's | Morphology |",
                "|---:|---|---|---|"]
        rendered = []

        for i, item in enumerate(data["words"], 1):
            s = ", ".join(item["strongs"])
            m = ", ".join(item["morphology"])
            rows.append(f"| {i} | {item['text']} | {s} | {m} |")

            links = " ".join(f"[[Strong's {x}]]" for x in item["strongs"])
            rendered.append(f"**{item['text']}** {links}".strip())

            words += 1
            tags += len(item["strongs"])
            morphs += len(item["morphology"])

        note = f"""---
type: verse
translation: KJV
source: CrossWire
osis: {data['osis']}
book: {book}
chapter: {chapter}
verse: {verse_no}
---

# {book} {chapter}:{verse_no}

## KJV

{data['text']}

## KJV + Strong's

{' '.join(rendered)}

## Word table

{chr(10).join(rows)}
"""
        path = VAULT/"KJV"/book/str(chapter)/f"{verse_no:03d}.md"
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
        "morphology_tags": morphs,
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--keep-raw",
        action="store_true",
        help="Keep downloaded module and extracted OSIS files."
    )
    args = parser.parse_args()

    sqlite = BUILD/"bible_mt_tr.sqlite"
    if sqlite.exists():
        raise RuntimeError(
            "Refusing to run because build/bible_mt_tr.sqlite exists. "
            "KJV importer must never touch the MT/TR SQLite database."
        )

    BUILD.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)

    archive = RAW/"KJV.zip"
    print("Downloading official CrossWire KJV module...")
    download(MODULE_URL, archive)

    extract = RAW/"module"
    if extract.exists():
        shutil.rmtree(extract)
    extract.mkdir()

    with zipfile.ZipFile(archive) as z:
        z.extractall(extract)

    xml_path = find_osis_xml(extract)
    print(f"Parsing CrossWire OSIS: {xml_path}")
    verses = parse_osis(xml_path)
    report = generate(verses)

    report.update({
        "source": {
            "name": "CrossWire KJV SWORD module",
            "module": "KJV",
            "version": "3.1",
            "module_info": MODULE_INFO,
            "download": MODULE_URL,
            "archive_sha256": sha256(archive),
        }
    })

    (BUILD/"build_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2)+"\n",
        encoding="utf-8"
    )
    (BUILD/"source_manifest.json").write_text(
        json.dumps({
            "source": report["source"],
            "archive": {
                "file": str(archive.relative_to(BUILD)),
                "sha256": sha256(archive),
                "bytes": archive.stat().st_size,
            },
            "osis": {
                "file": str(xml_path.relative_to(BUILD)),
                "sha256": sha256(xml_path),
                "bytes": xml_path.stat().st_size,
            },
        }, ensure_ascii=False, indent=2)+"\n",
        encoding="utf-8"
    )

    if not args.keep_raw:
        shutil.rmtree(RAW)

    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
