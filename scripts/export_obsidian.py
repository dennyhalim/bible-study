#!/usr/bin/env python3
"""Export SQLite to an Obsidian vault with live progress."""
from pathlib import Path
import json, re, shutil, sqlite3, time

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "build/bible_mt_tr.sqlite"
OUT = ROOT / "build/obsidian"

def safe_name(name):
    return re.sub(r'[\\/:*?"<>|]', "-", name)

def main():
    start = time.monotonic()
    if not DB.is_file():
        raise SystemExit(f"Missing database: {DB}")

    shutil.rmtree(OUT, ignore_errors=True)
    (OUT / "KJV").mkdir(parents=True)
    (OUT / "Strong's").mkdir(parents=True)

    con = sqlite3.connect(DB)
    books = con.execute(
        "SELECT book_id, code, name FROM book ORDER BY ordinal"
    ).fetchall()
    total_chapters = con.execute(
        "SELECT COUNT(*) FROM (SELECT DISTINCT book_id, chapter FROM verse)"
    ).fetchone()[0]

    print(f"[Obsidian] Starting export: {len(books)} books, {total_chapters} chapters",
          flush=True)

    chapter_no = 0
    for book_index, (book_id, code, name) in enumerate(books, 1):
        chapters = con.execute(
            "SELECT DISTINCT chapter FROM verse WHERE book_id=? ORDER BY chapter",
            (book_id,)
        ).fetchall()

        for chapter_index, (chapter,) in enumerate(chapters, 1):
            chapter_no += 1
            rows = con.execute(
                """SELECT v.verse, v.text_kjv,
                          w.surface, w.strongs_json, w.lemma, w.morphology
                   FROM verse v
                   LEFT JOIN word w ON w.verse_id=v.verse_id
                   WHERE v.book_id=? AND v.chapter=?
                   ORDER BY v.verse,w.position""",
                (book_id, chapter)
            ).fetchall()

            lines = [
                "---", "type: bible-chapter", f"book: {name}",
                f"book_code: {code}", f"chapter: {chapter}", "---", "",
                f"# {name} {chapter}", ""
            ]

            current = None
            for verse, text, surface, strongs_json, lemma, morphology in rows:
                if verse != current:
                    lines += [
                        f"## {name} {chapter}:{verse}", "",
                        text, "", "### Word data", ""
                    ]
                    current = verse

                if surface:
                    ids = json.loads(strongs_json or "[]")
                    links = " ".join(
                        f"[[Strong's/{sid}|{sid}]]" for sid in ids
                    )
                    meta = []
                    if lemma:
                        meta.append(f"lemma: `{lemma}`")
                    if morphology:
                        meta.append(f"morphology: `{morphology}`")
                    suffix = (" — " + " ".join(meta)) if meta else ""
                    if links:
                        suffix += f" — {links}"
                    lines.append(f"- `{surface}`{suffix}")

            path = OUT / "KJV" / safe_name(name) / f"{chapter:02d}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            if chapter_no == 1 or chapter_no % 25 == 0 or chapter_no == total_chapters:
                pct = chapter_no / total_chapters * 100
                elapsed = time.monotonic() - start
                print(
                    f"[Obsidian] {chapter_no}/{total_chapters} "
                    f"({pct:.1f}%) — {name} {chapter} — "
                    f"{elapsed:.1f}s elapsed",
                    flush=True
                )

    strongs_ids = con.execute("""
        SELECT DISTINCT json_each.value
        FROM word, json_each(word.strongs_json)
        WHERE json_each.value IS NOT NULL
        ORDER BY json_each.value
    """).fetchall()

    total_strongs = len(strongs_ids)
    print(f"[Obsidian] Generating {total_strongs} Strong's notes", flush=True)

    for index, (sid,) in enumerate(strongs_ids, 1):
        rows = con.execute(
            """SELECT DISTINCT b.name,v.chapter,v.verse
               FROM word w
               JOIN verse v ON v.verse_id=w.verse_id
               JOIN book b ON b.book_id=v.book_id
               WHERE EXISTS (
                 SELECT 1 FROM json_each(w.strongs_json)
                 WHERE value=?
               )
               ORDER BY b.ordinal,v.chapter,v.verse""",
            (sid,)
        ).fetchall()

        lines = [
            "---", "type: strongs", f"strongs: {sid}", "---", "",
            f"# Strong's {sid}", "",
            "> Lexical definition, lemma, and morphology are populated only "
            "when verified source datasets are imported.", "",
            "## Occurrences", ""
        ]

        for book, chapter, verse in rows:
            lines.append(
                f"- [[../KJV/{safe_name(book)}/{chapter:02d}#"
                f"{book} {chapter}:{verse}|{book} {chapter}:{verse}]]"
            )

        (OUT / "Strong's" / f"{sid}.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

        if index == 1 or index % 100 == 0 or index == total_strongs:
            pct = index / total_strongs * 100 if total_strongs else 100
            elapsed = time.monotonic() - start
            print(
                f"[Obsidian] Strong's {index}/{total_strongs} "
                f"({pct:.1f}%) — {elapsed:.1f}s elapsed",
                flush=True
            )

    con.close()
    elapsed = time.monotonic() - start
    chapter_files = len(list((OUT / "KJV").rglob("*.md")))
    strongs_files = len(list((OUT / "Strong's").glob("*.md")))
    print(
        f"[Obsidian] COMPLETE — {chapter_files} chapter files + "
        f"{strongs_files} Strong's files — {elapsed:.1f}s",
        flush=True
    )

if __name__ == "__main__":
    main()
