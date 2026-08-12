#!/usr/bin/env python3
"""
Build the canonical MT/TR SQLite database and a derived Obsidian vault.

SQLite deliberately excludes KJV.
Obsidian may include KJV + Strong's once a verified machine-readable dataset
is configured in config/sources.toml.

The downloader is intentionally strict: it never invents Strong's tags.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import urllib.request
import zipfile
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
DATA = BUILD / "data"
DB = BUILD / "bible_mt_tr.sqlite"
VAULT = BUILD / "obsidian-vault"
SCHEMA = ROOT / "config" / "schema.sql"

BOOKS = [
("Gen","Genesis"),("Exo","Exodus"),("Lev","Leviticus"),("Num","Numbers"),("Deu","Deuteronomy"),
("Jos","Joshua"),("Jdg","Judges"),("Rut","Ruth"),("1Sa","1 Samuel"),("2Sa","2 Samuel"),
("1Ki","1 Kings"),("2Ki","2 Kings"),("1Ch","1 Chronicles"),("2Ch","2 Chronicles"),
("Ezr","Ezra"),("Neh","Nehemiah"),("Est","Esther"),("Job","Job"),("Psa","Psalms"),
("Pro","Proverbs"),("Ecc","Ecclesiastes"),("Sng","Song of Solomon"),("Isa","Isaiah"),
("Jer","Jeremiah"),("Lam","Lamentations"),("Ezk","Ezekiel"),("Dan","Daniel"),
("Hos","Hosea"),("Jol","Joel"),("Amo","Amos"),("Oba","Obadiah"),("Jon","Jonah"),
("Mic","Micah"),("Nam","Nahum"),("Hab","Habakkuk"),("Zep","Zephaniah"),("Hag","Haggai"),
("Zec","Zechariah"),("Mal","Malachi"),
("Mat","Matthew"),("Mrk","Mark"),("Luk","Luke"),("Jhn","John"),("Act","Acts"),
("Rom","Romans"),("1Co","1 Corinthians"),("2Co","2 Corinthians"),("Gal","Galatians"),
("Eph","Ephesians"),("Php","Philippians"),("Col","Colossians"),("1Th","1 Thessalonians"),
("2Th","2 Thessalonians"),("1Ti","1 Timothy"),("2Ti","2 Timothy"),("Tit","Titus"),
("Phm","Philemon"),("Heb","Hebrews"),("Jas","James"),("1Pe","1 Peter"),("2Pe","2 Peter"),
("1Jn","1 John"),("2Jn","2 John"),("3Jn","3 John"),("Jud","Jude"),("Rev","Revelation")
]

def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()

def download(url: str, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "BibleMTTRBuilder/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r, dest.open("wb") as f:
        shutil.copyfileobj(r, f)

def write_source_manifest(conn):
    rows = conn.execute(
        "SELECT name,url,license,sha256,downloaded_at,notes FROM sources ORDER BY name"
    ).fetchall()
    (BUILD / "source_manifest.json").write_text(
        json.dumps([dict(zip(
            ["name","url","license","sha256","downloaded_at","notes"], r
        )) for r in rows], ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

def create_db():
    if DB.exists():
        DB.unlink()
    conn = sqlite3.connect(DB)
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    for i, (osis, name) in enumerate(BOOKS, 1):
        testament = "OT" if i <= 39 else "NT"
        conn.execute(
            "INSERT INTO books VALUES (?,?,?,?,?)",
            (i, testament, osis, name, i)
        )
    conn.commit()
    return conn

def safe_write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

def generate_obsidian(conn):
    if VAULT.exists():
        shutil.rmtree(VAULT)

    safe_write(VAULT / "_meta" / "README.md", """# Bible MT/TR Research Vault

This vault is generated from `bible_mt_tr.sqlite`.

## Source policy

- MT/WLC and TR are the controlling textual layers.
- KJV is reference-only and is not stored in SQLite.
- KJV + Strong's is included only when a verified machine-readable source is configured.
- Lexicons and morphology are supporting data, not replacement texts.

The vault is regenerated from SQLite; do not treat generated files as the canonical database.
""")

    # Lemmas
    for row in conn.execute("""
        SELECT l.id,l.language,l.lemma,l.transliteration,l.root,
               s.code,g.core_gloss,g.semantic_range
        FROM lemmas l
        LEFT JOIN strongs s ON s.lemma_id=l.id
        LEFT JOIN glossary g ON g.lemma_id=l.id AND g.language='id'
        ORDER BY l.language,l.normalized
    """):
        lid, lang, lemma, translit, root, strong, gloss, semrange = row
        safe = re.sub(r'[\\/:*?"<>|]', "_", lemma)
        note = f"""---
type: lemma
language: {lang}
lemma: {lemma}
strongs: {strong or ""}
---

# {lemma}

**Transliteration:** {translit or ""}  
**Strong's:** {strong or ""}  
**Core Indonesian gloss:** {gloss or ""}

## Semantic range

{semrange or ""}

## Occurrences

```dataview
TABLE reference, surface, morphology_code, strongs_code
FROM "Verses"
WHERE lemma_id = {lid}
SORT reference
```
"""
        safe_write(VAULT / "Lemmas" / lang / f"{safe}.md", note)

    # Strong's
    for code, lang, gloss, definition in conn.execute(
        "SELECT code,language,gloss,definition FROM strongs ORDER BY code"
    ):
        safe_write(
            VAULT / "Strongs" / f"{code}.md",
            f"""---
type: strongs
code: {code}
language: {lang}
source_role: lexical_reference
---

# {code}

**Language:** {lang}  
**Gloss:** {gloss or ""}

## Definition

{definition or ""}

## Occurrences

```dataview
TABLE reference, surface, lemma, morphology_code
FROM "Verses"
WHERE strongs_code = "{code}"
SORT reference
```
"""
        )

    # Verse notes with TR/MT word-level links.
    for vid, ref, osis, name, chapter, verse in conn.execute("""
        SELECT v.id,v.reference,b.osis,b.name,v.chapter,v.verse
        FROM verses v JOIN books b ON b.id=v.book_id
        ORDER BY b.sort_order,v.chapter,v.verse
    """):
        rows = conn.execute("""
            SELECT w.surface,l.lemma,s.code,m.code
            FROM words w
            LEFT JOIN lemmas l ON l.id=w.lemma_id
            LEFT JOIN strongs s ON s.id=w.strongs_id
            LEFT JOIN morphology m ON m.id=w.morphology_id
            WHERE w.verse_id=?
            ORDER BY w.position
        """,(vid,)).fetchall()
        table = ["| # | Source word | Lemma | Strong's | Morphology |",
                 "|---:|---|---|---|---|"]
        for i,(surface,lemma,strong,morph) in enumerate(rows,1):
            table.append(
                f"| {i} | {surface} | {lemma or ''} | {strong or ''} | {morph or ''} |"
            )
        note = f"""---
type: verse
reference: {ref}
testament: {"OT" if osis in [x[0] for x in BOOKS[:39]] else "NT"}
text_layer: {"MT/WLC" if osis in [x[0] for x in BOOKS[:39]] else "TR"}
---

# {name} {chapter}:{verse}

## Source Word Analysis

{chr(10).join(table)}

## Translation

- Literal: 
- Natural Indonesian: 

## Translation Decisions

_No decisions recorded yet._

## Opus Audit

_Status: pending._
"""
        safe_write(VAULT / "Verses" / name / str(chapter) / f"{verse:03}.md", note)

    # KJV import is intentionally a separate, strict adapter.
    cfg = tomllib.loads((ROOT/"config"/"sources.toml").read_text(encoding="utf-8"))
    kjv_url = cfg.get("kjv",{}).get("url","").strip()
    if kjv_url:
        raise SystemExit(
            "KJV adapter is configured but not implemented in this build: "
            "provide a verified machine-readable KJV+Strong's parser before enabling it."
        )
    safe_write(VAULT / "_meta" / "KJV.md", """# KJV + Strong's

KJV + Strong's is intentionally not populated until a verified machine-readable
dataset is configured. The pipeline will not guess Strong's tagging.
""")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args()

    BUILD.mkdir(exist_ok=True)
    DATA.mkdir(exist_ok=True)

    # Current stage: create the canonical database and derived vault.
    # Source adapters are isolated so exact upstream file formats can be pinned
    # and validated without contaminating the core schema.
    conn = create_db()
    generate_obsidian(conn)

    report = {
        "books": conn.execute("SELECT COUNT(*) FROM books").fetchone()[0],
        "verses": conn.execute("SELECT COUNT(*) FROM verses").fetchone()[0],
        "words": conn.execute("SELECT COUNT(*) FROM words").fetchone()[0],
        "lemmas": conn.execute("SELECT COUNT(*) FROM lemmas").fetchone()[0],
        "strongs": conn.execute("SELECT COUNT(*) FROM strongs").fetchone()[0],
        "morphology": conn.execute("SELECT COUNT(*) FROM morphology").fetchone()[0],
        "lexicon_entries": conn.execute("SELECT COUNT(*) FROM lexicon_entries").fetchone()[0],
        "kjv_in_sqlite": False,
        "kjv_obsidian": "not populated until verified dataset configured"
    }
    conn.close()

    (BUILD/"build_report.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2), encoding="utf-8"
    )

    hashes = []
    for p in [DB, BUILD/"build_report.json", BUILD/"source_manifest.json"]:
        if p.exists():
            hashes.append(f"{sha256(p)}  {p.name}")
    (BUILD/"SHA256SUMS").write_text("\n".join(hashes)+"\n", encoding="utf-8")

    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__ == "__main__":
    main()
