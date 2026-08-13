#!/usr/bin/env python3
"""Export SQLite to an Obsidian vault: one KJV chapter per Markdown file."""
from pathlib import Path
import json, re, shutil, sqlite3

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "build/bible_mt_tr.sqlite"
OUT = ROOT / "build/obsidian"

def safe_name(name):
    return re.sub(r'[\\/:*?"<>|]', "-", name)

def main():
    if not DB.is_file():
        raise SystemExit(f"Missing database: {DB}")

    shutil.rmtree(OUT, ignore_errors=True)
    (OUT / "KJV").mkdir(parents=True)
    (OUT / "Strong's").mkdir(parents=True)

    con = sqlite3.connect(DB)
    books = con.execute(
        "SELECT book_id, code, name FROM book ORDER BY ordinal"
    ).fetchall()

    for book_id, code, name in books:
        chapters = con.execute(
            """SELECT DISTINCT chapter FROM verse
               WHERE book_id=? ORDER BY chapter""",
            (book_id,)
        ).fetchall()

        for (chapter,) in chapters:
            lines = [
                "---",
                "type: bible-chapter",
                f"book: {name}",
                f"book_code: {code}",
                f"chapter: {chapter}",
                "---",
                "",
                f"# {name} {chapter}",
                "",
            ]

            rows = con.execute(
                """SELECT v.verse, v.text_kjv,
                          w.surface, w.strongs_json, w.lemma, w.morphology
                   FROM verse v
                   LEFT JOIN word w ON w.verse_id=v.verse_id
                   WHERE v.book_id=? AND v.chapter=?
                   ORDER BY v.verse, w.position""",
                (book_id, chapter)
            ).fetchall()

            current = None
            for verse, text, surface, strongs_json, lemma, morphology in rows:
                if verse != current:
                    lines += [
                        f"## [[{safe_name(name)}/{chapter:02d}#{name} {chapter}:{verse}|{name} {chapter}:{verse}]]",
                        "",
                        text,
                        "",
                        "### Word data",
                        "",
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
                    suffix = " — " + " ".join(meta) if meta else ""
                    if links:
                        suffix += f" — {links}"
                    lines.append(f"- `{surface}`{suffix}")

            path = OUT / "KJV" / safe_name(name) / f"{chapter:02d}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    strongs_ids = con.execute("""
        SELECT DISTINCT json_each.value
        FROM word, json_each(word.strongs_json)
        WHERE json_each.value IS NOT NULL
        ORDER BY json_each.value
    """).fetchall()

    for (sid,) in strongs_ids:
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
            "---",
            "type: strongs",
            f"strongs: {sid}",
            "---",
            "",
            f"# Strong's {sid}",
            "",
            "> Lexical definition, lemma, and morphology are populated only "
            "when verified source datasets are imported.",
            "",
            "## Occurrences",
            "",
        ]

        for book, chapter, verse in rows:
            lines.append(
                f"- [[../KJV/{safe_name(book)}/{chapter:02d}#"
                f"{book} {chapter}:{verse}|{book} {chapter}:{verse}]]"
            )

        (OUT / "Strong's" / f"{sid}.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

    con.close()

if __name__ == "__main__":
    main()
