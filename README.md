# KJV + Strong's Obsidian Builder

This package builds the KJV + Strong's reference layer separately from the
MT/TR SQLite database.

## Current source

The previous jsonBible endpoint was returning 404. The current public static
source is **BibleEngine**, which documents these files:

- `https://bibleengine.org/v1/kjv/manifest.json`
- `https://bibleengine.org/v1/kjvstrongs/{BB}/{CCC}.json`

The manifest supplies the 66 books and per-chapter verse counts, so the builder
does not guess chapter boundaries.

## Output

```text
build/
├── build_report.json
├── source_manifest.json
├── raw/
└── obsidian-kjv/
    └── KJV/
        └── Book/Chapter/Verse.md
```

Validation requires 66 books and exactly 31,102 verses.

## SQLite separation

The importer refuses to run if `build/bible_mt_tr.sqlite` exists and never
opens or writes that database.

## CrossWire

CrossWire is not required for the primary build. This keeps the build from
failing because an independent audit source is unavailable.

## Dependencies

Python standard library only. No `requirements.txt` or pip packages.
