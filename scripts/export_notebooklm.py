#!/usr/bin/env python3
"""Fast Gemini/NotebookLM exporter.

Uses bulk SQLite reads rather than one query per Strong's ID.
Outputs one Markdown source per Bible book plus merged Strong's indexes.
"""
from pathlib import Path
from collections import defaultdict
import json, sqlite3, time, shutil, argparse

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "build/bible_mt_tr.sqlite"
OUT = ROOT / "build/notebooklm"

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--strongs-per-file", type=int, default=2000)
    return p.parse_args()

def load_occurrences(con):
    print("[Gemini] Loading all Strong's occurrences in one SQL query...", flush=True)
    occurrence = defaultdict(list)
    rows = con.execute("""
        SELECT json_each.value, b.name, v.chapter, v.verse
        FROM word AS w
        JOIN verse AS v ON v.verse_id = w.verse_id
        JOIN book AS b ON b.book_id = v.book_id
        JOIN json_each(w.strongs_json)
        ORDER BY json_each.value, b.ordinal, v.chapter, v.verse
    """).fetchall()

    for sid, book, chapter, verse in rows:
        occurrence[sid].append((book, chapter, verse))

    print(
        f"[Gemini] Loaded {len(occurrence)} Strong's IDs / "
        f"{len(rows)} occurrence rows",
        flush=True,
    )
    return occurrence

def bucket(sid, size):
    n = int(sid[1:])
    lo = (n // size) * size
    hi = lo + size - 1
    return f"{sid[0]}{lo:04d}-{hi:04d}"

def export_books(con, start):
    books = con.execute(
        "SELECT book_id, name FROM book ORDER BY ordinal"
    ).fetchall()
    total = len(books)

    for i, (book_id, name) in enumerate(books, 1):
        rows = con.execute("""
            SELECT v.chapter, v.verse, v.text_kjv,
                   w.surface, w.strongs_json, w.lemma, w.morphology
            FROM verse AS v
            LEFT JOIN word AS w ON w.verse_id = v.verse_id
            WHERE v.book_id = ?
            ORDER BY v.chapter, v.verse, w.position
        """, (book_id,)).fetchall()

        lines = [
            f"# {name} — KJV + Strong's",
            "",
            "Source: KJV2006 USFX.",
            "Strong's tags are preserved from the imported source.",
            "Lemma/morphology are shown only when populated by verified datasets.",
            "",
        ]

        current = None
        for chapter, verse, text, surface, strongs_json, lemma, morphology in rows:
            key = (chapter, verse)
            if key != current:
                if current is not None:
                    lines.append("")
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
                suffix = f"; {'; '.join(details)}" if details else ""
                lines.append(f"- {surface} -> {ids}{suffix}")

        (OUT / f"{name}.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

        elapsed = time.monotonic() - start
        print(
            f"[Gemini] books {i}/{total} ({i/total*100:.1f}%) — "
            f"{name} — {elapsed:.1f}s",
            flush=True,
        )

def export_strongs(occurrence, start, per_file):
    ids = sorted(occurrence, key=lambda x: (x[0], int(x[1:])))
    groups = defaultdict(list)
    for sid in ids:
        groups[bucket(sid, per_file)].append(sid)

    path = OUT / "Strongs"
    path.mkdir(parents=True, exist_ok=True)

    print(
        f"[Gemini] Writing {len(ids)} Strong's IDs into "
        f"{len(groups)} merged files",
        flush=True,
    )

    done = 0
    for group in sorted(groups):
        lines = [
            "# Strong's occurrence index",
            "",
            f"## Range {group}",
            "",
        ]

        for sid in groups[group]:
            lines += [f"### {sid}", ""]
            refs = occurrence[sid]
            if refs:
                lines.append("; ".join(f"{b} {c}:{v}" for b, c, v in refs))
            else:
                lines.append("No occurrences recorded.")
            lines.append("")
            done += 1

        (path / f"{group}.md").write_text(
            "\n".join(lines), encoding="utf-8"
        )

        elapsed = time.monotonic() - start
        print(
            f"[Gemini] Strong's {done}/{len(ids)} "
            f"({done/len(ids)*100:.1f}%) — {group} — {elapsed:.1f}s",
            flush=True,
        )

def main():
    a = parse_args()
    if a.strongs_per_file < 1:
        raise SystemExit("--strongs-per-file must be >= 1")
    if not DB.is_file():
        raise SystemExit(f"Missing database: {DB}")

    start = time.monotonic()
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)

    con = sqlite3.connect(DB)
    con.execute("PRAGMA temp_store=MEMORY")
    con.execute("PRAGMA cache_size=-65536")

    print("[Gemini] FAST exporter starting", flush=True)

    # One bulk Strong's query is shared by the whole export.
    occurrence = load_occurrences(con)
    export_books(con, start)
    export_strongs(occurrence, start, a.strongs_per_file)

    con.close()

    book_files = len(list(OUT.glob("*.md")))
    strongs_files = len(list((OUT / "Strongs").glob("*.md")))
    elapsed = time.monotonic() - start
    print(
        f"[Gemini] COMPLETE — {book_files} book files + "
        f"{strongs_files} Strong's files — {elapsed:.1f}s",
        flush=True,
    )

if __name__ == "__main__":
    main()
