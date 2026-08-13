#!/usr/bin/env python3
"""Export compact, self-contained Markdown sources for NotebookLM/Gemini."""
from pathlib import Path
import json, shutil, sqlite3

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "build/bible_mt_tr.sqlite"
OUT = ROOT / "build/notebooklm"

def main():
    if not DB.is_file():
        raise SystemExit(f"Missing database: {DB}")

    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)

    con = sqlite3.connect(DB)
    books = con.execute(
        "SELECT book_id, name FROM book ORDER BY ordinal"
    ).fetchall()

    for book_id, name in books:
        rows = con.execute(
            """SELECT v.chapter,v.verse,v.text_kjv,
                      w.surface,w.strongs_json,w.lemma,w.morphology
               FROM verse v
               LEFT JOIN word w ON w.verse_id=v.verse_id
               WHERE v.book_id=?
               ORDER BY v.chapter,v.verse,w.position""",
            (book_id,)
        ).fetchall()

        lines = [
            f"# {name} — KJV + Strong's",
            "",
            "Source: KJV2006 USFX. Strong's tags are preserved from the source.",
            "Lemma/morphology fields are left empty until verified TR/MT datasets are imported.",
            "",
        ]

        current = None
        for chapter, verse, text, surface, strongs_json, lemma, morphology in rows:
            key = (chapter, verse)
            if key != current:
                lines += [
                    f"## {name} {chapter}:{verse}",
                    "",
                    f"KJV: {text}",
                    "",
                    "Word alignment:",
                ]
                current = key

            if surface:
                ids = ", ".join(json.loads(strongs_json or "[]")) or "none"
                details = []
                if lemma:
                    details.append(f"lemma={lemma}")
                if morphology:
                    details.append(f"morphology={morphology}")
                extra = f"; {'; '.join(details)}" if details else ""
                lines.append(f"- {surface} -> {ids}{extra}")

            if key != (chapter, verse):
                lines.append("")

        (OUT / f"{name}.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

    index = ["# Strong's occurrence index", ""]
    ids = con.execute("""
        SELECT DISTINCT json_each.value
        FROM word, json_each(word.strongs_json)
        WHERE json_each.value IS NOT NULL
        ORDER BY json_each.value
    """).fetchall()

    for (sid,) in ids:
        refs = con.execute(
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
        index += [
            f"## {sid}",
            ", ".join(f"{b} {c}:{v}" for b,c,v in refs),
            "",
        ]

    (OUT / "Strong's occurrence index.md").write_text(
        "\n".join(index) + "\n", encoding="utf-8"
    )
    con.close()

if __name__ == "__main__":
    main()
