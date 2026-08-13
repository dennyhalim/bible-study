#!/usr/bin/env python3
"""Export compact Markdown sources for NotebookLM/Gemini with live progress."""
from pathlib import Path
import json, shutil, sqlite3, time

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "build/bible_mt_tr.sqlite"
OUT = ROOT / "build/notebooklm"

def main():
    start = time.monotonic()
    if not DB.is_file():
        raise SystemExit(f"Missing database: {DB}")

    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)

    con = sqlite3.connect(DB)
    books = con.execute(
        "SELECT book_id, name FROM book ORDER BY ordinal"
    ).fetchall()
    total = len(books)

    print(f"[Gemini] Starting export: {total} books", flush=True)

    for index, (book_id, name) in enumerate(books, 1):
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
            f"# {name} — KJV + Strong's", "",
            "Source: KJV2006 USFX. Strong's tags are preserved from the source.",
            "Lemma/morphology fields are left empty until verified TR/MT datasets are imported.",
            ""
        ]

        current = None
        for chapter, verse, text, surface, strongs_json, lemma, morphology in rows:
            key = (chapter, verse)
            if key != current:
                if current is not None:
                    lines.append("")
                lines += [f"## {name} {chapter}:{verse}", "", f"KJV: {text}", "",
                           "Word alignment:"]
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

        (OUT / f"{name}.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

        elapsed = time.monotonic() - start
        print(
            f"[Gemini] {index}/{total} ({index/total*100:.1f}%) — "
            f"{name} — {elapsed:.1f}s elapsed",
            flush=True
        )

    print("[Gemini] Building Strong's occurrence index", flush=True)

    index_lines = ["# Strong's occurrence index", ""]
    ids = con.execute("""
        SELECT DISTINCT json_each.value
        FROM word, json_each(word.strongs_json)
        WHERE json_each.value IS NOT NULL
        ORDER BY json_each.value
    """).fetchall()

    total_ids = len(ids)
    for index, (sid,) in enumerate(ids, 1):
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
        index_lines += [
            f"## {sid}",
            ", ".join(f"{b} {c}:{v}" for b,c,v in refs), ""
        ]

        if index == 1 or index % 100 == 0 or index == total_ids:
            print(
                f"[Gemini] Strong's index {index}/{total_ids} "
                f"({index/total_ids*100:.1f}%)",
                flush=True
            )

    (OUT / "Strong's occurrence index.md").write_text(
        "\n".join(index_lines) + "\n", encoding="utf-8"
    )
    con.close()

    elapsed = time.monotonic() - start
    print(
        f"[Gemini] COMPLETE — {total} book files + Strong's index — "
        f"{elapsed:.1f}s",
        flush=True
    )

if __name__ == "__main__":
    main()
