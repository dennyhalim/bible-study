# KJV + Strong's — eBible.org importer

## Primary source

This build uses the explicitly published eBible.org KJV2006 USFX archive:

https://ebible.org/Scriptures/eng-kjv2006_usfx.zip

The eBible source page identifies `ENGKJV / eng-kjv2006` as:

- King James Version
- standardized 1769 text
- protocanon only
- Strong's numbers added
- public domain
- supplied courtesy of CrossWire Bible Society and eBible.org

Source page:
https://ebible.org/find/show.php?id=eng-kjv2006

The eBible download directory currently lists the exact USFX archive, so the
workflow does not depend on guessed CrossWire FTP paths or undocumented APIs.

## Why this replaces the previous importers

Previous builds used endpoints that returned 404/non-JSON responses. This build
uses a stable, explicitly published downloadable archive and records SHA-256
checksums in `source_manifest.json`.

## Output

```text
build/
├── build_report.json
├── source_manifest.json
└── obsidian-kjv/
    └── KJV/
        └── Book/Chapter/Verse.md
```

The build requires exactly 66 books and 31,102 verses.

## SQLite separation

`bible_mt_tr.sqlite` is never opened, created, or modified. The importer
actively refuses to run if that file already exists under `build/`.

## Dependencies

Python standard library only.
