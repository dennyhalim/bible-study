#!/usr/bin/env python3
"""Build the canonical temporary SQLite database from KJV2006 USFX."""
from pathlib import Path
import json, re, sqlite3
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "vendor/kjv2006/eng-kjv2006_usfx.xml"
OUT = ROOT / "build/bible_mt_tr.sqlite"

BOOKS = [
("GEN","Genesis"),("EXO","Exodus"),("LEV","Leviticus"),("NUM","Numbers"),("DEU","Deuteronomy"),
("JOS","Joshua"),("JDG","Judges"),("RUT","Ruth"),("1SA","1 Samuel"),("2SA","2 Samuel"),
("1KI","1 Kings"),("2KI","2 Kings"),("1CH","1 Chronicles"),("2CH","2 Chronicles"),
("EZR","Ezra"),("NEH","Nehemiah"),("EST","Esther"),("JOB","Job"),("PSA","Psalms"),
("PRO","Proverbs"),("ECC","Ecclesiastes"),("SNG","Song of Solomon"),("ISA","Isaiah"),
("JER","Jeremiah"),("LAM","Lamentations"),("EZK","Ezekiel"),("DAN","Daniel"),
("HOS","Hosea"),("JOL","Joel"),("AMO","Amos"),("OBA","Obadiah"),("JON","Jonah"),
("MIC","Micah"),("NAM","Nahum"),("HAB","Habakkuk"),("ZEP","Zephaniah"),("HAG","Haggai"),
("ZEC","Zechariah"),("MAL","Malachi"),("MAT","Matthew"),("MRK","Mark"),("LUK","Luke"),
("JHN","John"),("ACT","Acts"),("ROM","Romans"),("1CO","1 Corinthians"),("2CO","2 Corinthians"),
("GAL","Galatians"),("EPH","Ephesians"),("PHP","Philippians"),("COL","Colossians"),
("1TH","1 Thessalonians"),("2TH","2 Thessalonians"),("1TI","1 Timothy"),("2TI","2 Timothy"),
("TIT","Titus"),("PHM","Philemon"),("HEB","Hebrews"),("JAS","James"),("1PE","1 Peter"),
("2PE","2 Peter"),("1JN","1 John"),("2JN","2 John"),("3JN","3 John"),("JUD","Jude"),("REV","Revelation")
]
BOOK_BY_CODE = dict(BOOKS)

def tag(node):
    return node.rsplit("}", 1)[-1].lower()

def clean(text):
    return " ".join(text.split())

def strongs(attrs):
    result = []
    for key, value in attrs.items():
        if key.lower() in {"s", "strong", "lemma", "l"} or "strong" in key.lower():
            for item in re.findall(r"\b[GH]\d{1,5}\b", value.upper()):
                if item not in result:
                    result.append(item)
    return result

def parse():
    root = ET.parse(SOURCE).getroot()
    verses = []
    words = []

    for book in root.iter():
        if tag(book.tag) != "book":
            continue
        code = (book.attrib.get("id") or "").upper().split()[0]
        if code not in BOOK_BY_CODE:
            continue

        chapter = None
        active = None

        def walk(node, active):
            nonlocal chapter
            kind = tag(node.tag)

            if kind == "c":
                match = re.search(r"\d+", node.attrib.get("id", ""))
                if match:
                    chapter = int(match.group())
                return active

            if kind == "v":
                raw = node.attrib.get("id", "")
                match = re.search(r"(?:^|[.\s])(\d+)\.(\d+)", raw)
                if match:
                    chapter, verse = map(int, match.groups())
                else:
                    match = re.search(r"\d+", raw)
                    if not match or chapter is None:
                        return active
                    verse = int(match.group())

                active = (code, chapter, verse)
                verses.append(active)
                return active

            if kind == "w" and active:
                surface = clean("".join(node.itertext()))
                if surface:
                    words.append((active, surface, json.dumps(
                        strongs(node.attrib), ensure_ascii=False)))
                return active

            for child in node:
                active = walk(child, active)
            return active

        for child in book:
            active = walk(child, active)

    verses = list(dict.fromkeys(verses))
    grouped = {}
    for ref, surface, _ in words:
        grouped.setdefault(ref, []).append(surface)
    return verses, words, grouped

def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.unlink(missing_ok=True)

    verses, words, grouped = parse()
    con = sqlite3.connect(OUT)

    con.executescript("""
    PRAGMA foreign_keys=ON;

    CREATE TABLE metadata(
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL
    );

    CREATE TABLE book(
      book_id INTEGER PRIMARY KEY,
      code TEXT UNIQUE NOT NULL,
      name TEXT UNIQUE NOT NULL,
      ordinal INTEGER NOT NULL
    );

    CREATE TABLE verse(
      verse_id INTEGER PRIMARY KEY,
      book_id INTEGER NOT NULL REFERENCES book(book_id),
      chapter INTEGER NOT NULL,
      verse INTEGER NOT NULL,
      text_kjv TEXT NOT NULL,
      UNIQUE(book_id, chapter, verse)
    );

    CREATE TABLE word(
      word_id INTEGER PRIMARY KEY,
      verse_id INTEGER NOT NULL REFERENCES verse(verse_id),
      position INTEGER NOT NULL,
      surface TEXT NOT NULL,
      strongs_json TEXT NOT NULL,
      lemma TEXT,
      morphology TEXT,
      UNIQUE(verse_id, position)
    );

    CREATE TABLE translation_decision(
      decision_id INTEGER PRIMARY KEY,
      verse_id INTEGER REFERENCES verse(verse_id),
      word_id INTEGER REFERENCES word(word_id),
      source TEXT,
      target TEXT,
      rationale TEXT,
      status TEXT
    );

    CREATE INDEX idx_verse_ref ON verse(book_id, chapter, verse);
    CREATE INDEX idx_word_verse ON word(verse_id);
    """)

    con.executemany(
        "INSERT INTO book VALUES(?,?,?,?)",
        [(i, code, name, i) for i, (code, name) in enumerate(BOOKS, 1)]
    )

    ref_to_id = {}
    for code, chapter, verse in verses:
        book_id = next(i for i, item in enumerate(BOOKS, 1) if item[0] == code)
        text = clean(" ".join(grouped.get((code, chapter, verse), [])))
        cur = con.execute(
            """INSERT INTO verse(book_id,chapter,verse,text_kjv)
               VALUES(?,?,?,?)""",
            (book_id, chapter, verse, text)
        )
        ref_to_id[(code, chapter, verse)] = cur.lastrowid

    positions = {}
    for ref, surface, strongs_json in words:
        verse_id = ref_to_id.get(ref)
        if not verse_id:
            continue
        positions[verse_id] = positions.get(verse_id, 0) + 1
        con.execute(
            """INSERT INTO word
               (verse_id,position,surface,strongs_json,lemma,morphology)
               VALUES(?,?,?,?,?,?)""",
            (verse_id, positions[verse_id], surface, strongs_json, None, None)
        )

    con.executemany("INSERT INTO metadata VALUES(?,?)", [
        ("schema_version", "1"),
        ("kjv_source", "eBible.org eng-kjv2006_usfx.xml"),
        ("lemma_morphology",
         "Reserved for verified TR/MT lexical and morphology datasets."),
    ])

    con.commit()
    integrity = con.execute("PRAGMA integrity_check").fetchone()[0]

    report = {
        "books": con.execute("SELECT COUNT(*) FROM book").fetchone()[0],
        "verses": con.execute("SELECT COUNT(*) FROM verse").fetchone()[0],
        "words": con.execute("SELECT COUNT(*) FROM word").fetchone()[0],
        "strongs_tags": sum(
            len(json.loads(row[0]))
            for row in con.execute("SELECT strongs_json FROM word")
        ),
        "integrity": integrity,
    }
    con.close()

    (ROOT / "build/sqlite_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    print(json.dumps(report, indent=2))
    if integrity != "ok":
        raise SystemExit("SQLite integrity check failed")

if __name__ == "__main__":
    main()
