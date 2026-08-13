#!/usr/bin/env python3
"""Fast Obsidian exporter.

Key optimization:
- Fetch all Strong's occurrences with one SQLite query.
- Group occurrences in Python.
- Write batched Strong's Markdown files (default 1000 entries/file).
- Avoid one SQL query per Strong's ID.
"""
from pathlib import Path
from collections import defaultdict
import json, re, shutil, sqlite3, time, argparse

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "build/bible_mt_tr.sqlite"
OUT = ROOT / "build/obsidian"

def safe_name(name):
    return re.sub(r'[\\/:*?"<>|]', "-", name)

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--strongs-per-file", type=int, default=1000)
    return p.parse_args()

def export_chapters(con, start):
    books = con.execute(
        "SELECT book_id, code, name FROM book ORDER BY ordinal"
    ).fetchall()
    total = con.execute(
        "SELECT COUNT(*) FROM (SELECT DISTINCT book_id, chapter FROM verse)"
    ).fetchone()[0]

    done = 0
    for book_id, code, name in books:
        chapters = con.execute(
            "SELECT DISTINCT chapter FROM verse WHERE book_id=? ORDER BY chapter",
            (book_id,)
        ).fetchall()

        for chapter, in chapters:
            rows = con.execute(
                """SELECT v.verse,v.text_kjv,w.surface,w.strongs_json,
                          w.lemma,w.morphology
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
                        f"[[Strong's/{bucket}#{sid}|{sid}]]"
                        for sid in ids
                        for bucket in [f"{sid[0]}{(int(sid[1:]) // 1000) * 1000:04d}-"
                                       f"{(int(sid[1:]) // 1000 + 1) * 1000 - 1:04d}"]
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

            done += 1
            if done == 1 or done % 50 == 0 or done == total:
                elapsed = time.monotonic() - start
                print(
                    f"[Obsidian] chapters {done}/{total} "
                    f"({done/total*100:.1f}%) — {elapsed:.1f}s",
                    flush=True
                )

def load_strongs_occurrences(con):
    """One bulk query instead of one query per Strong's ID."""
    print("[Obsidian] Loading all Strong's occurrences in one SQL query...",
          flush=True)

    occurrence = defaultdict(list)

    rows = con.execute("""
        SELECT
            json_each.value AS strongs,
            b.name,
            v.chapter,
            v.verse
        FROM word AS w
        JOIN verse AS v ON v.verse_id = w.verse_id
        JOIN book AS b ON b.book_id = v.book_id
        JOIN json_each(w.strongs_json)
        ORDER BY json_each.value, b.ordinal, v.chapter, v.verse
    """).fetchall()

    for sid, book, chapter, verse in rows:
        occurrence[sid].append((book, chapter, verse))

    print(
        f"[Obsidian] Loaded {len(occurrence)} Strong's IDs / "
        f"{len(rows)} occurrence rows",
        flush=True
    )
    return occurrence

def bucket_for(sid, size):
    n = int(sid[1:])
    lo = (n // size) * size
    hi = lo + size - 1
    return f"{sid[0]}{lo:04d}-{hi:04d}"

def export_strongs(con, start, per_file):
    occurrence = load_strongs_occurrences(con)
    ids = sorted(occurrence, key=lambda x: (x[0], int(x[1:])))
    total = len(ids)

    # Remove old Strong's output only; chapter files remain untouched.
    strongs_dir = OUT / "Strong's"
    shutil.rmtree(strongs_dir, ignore_errors=True)
    strongs_dir.mkdir(parents=True)

    groups = defaultdict(list)
    for sid in ids:
        groups[bucket_for(sid, per_file)].append(sid)

    print(
        f"[Obsidian] Writing {total} Strong's IDs into "
        f"{len(groups)} merged files ({per_file} IDs/file max)",
        flush=True
    )

    done = 0
    for bucket in sorted(groups):
        lines = [
            "---",
            "type: strongs-index",
            f"range: {bucket}",
            "---",
            "",
            f"# Strong's {bucket}",
            "",
        ]

        for sid in groups[bucket]:
            lines += [f"## {sid}", ""]
            refs = occurrence[sid]
            if refs:
                for book, chapter, verse in refs:
                    lines.append(
                        f"- [[../KJV/{safe_name(book)}/{chapter:02d}#"
                        f"{book} {chapter}:{verse}|{book} {chapter}:{verse}]]"
                    )
            else:
                lines.append("- No occurrences recorded.")
            lines.append("")
            done += 1

        (strongs_dir / f"{bucket}.md").write_text(
            "\n".join(lines), encoding="utf-8"
        )

        elapsed = time.monotonic() - start
        print(
            f"[Obsidian] Strong's {done}/{total} "
            f"({done/total*100:.1f}%) — wrote {bucket} — "
            f"{elapsed:.1f}s",
            flush=True
        )

    return total, len(groups)

def main():
    args = parse_args()
    if args.strongs_per_file < 1:
        raise SystemExit("--strongs-per-file must be >= 1")
    if not DB.is_file():
        raise SystemExit(f"Missing database: {DB}")

    start = time.monotonic()
    shutil.rmtree(OUT, ignore_errors=True)
    (OUT / "KJV").mkdir(parents=True)
    (OUT / "Strong's").mkdir(parents=True)

    con = sqlite3.connect(DB)
    con.execute("PRAGMA journal_mode=OFF")
    con.execute("PRAGMA synchronous=OFF")
    con.execute("PRAGMA temp_store=MEMORY")
    con.execute("PRAGMA cache_size=-65536")

    print("[Obsidian] FAST exporter starting", flush=True)
    export_chapters(con, start)
    strongs_total, strongs_files = export_strongs(
        con, start, args.strongs_per_file
    )
    con.close()

    chapter_files = len(list((OUT/"KJV").rglob("*.md")))
    elapsed = time.monotonic() - start
    print(
        f"[Obsidian] COMPLETE — {chapter_files} chapter files + "
        f"{strongs_files} merged Strong's files containing "
        f"{strongs_total} IDs — {elapsed:.1f}s",
        flush=True
    )

if __name__ == "__main__":
    main()
