# KJV + Strong's — CrossWire importer

This is the KJV + Strong's Obsidian reference layer.

## Source

CrossWire SWORD module:

- Module: `KJV`
- Version: `3.1`
- Description: KJV 1769 with Strong's Numbers, Morphology, and CatchWords
- Official module information:
  https://www.crosswire.org/sword/modules/ModInfo.jsp?modName=KJV

The importer downloads the raw KJV SWORD module directly from CrossWire,
extracts its OSIS/XML data, validates the parsed verse count, and generates
31,102 Markdown verse notes.

## Why this source

Unlike an undocumented JSON API, the SWORD module is an established,
versioned distribution artifact maintained by CrossWire.

## Output

```text
build/
├── build_report.json
├── source_manifest.json
└── obsidian-kjv/
    └── KJV/
        └── Book/Chapter/Verse.md
```

## SQLite

The importer refuses to run when `build/bible_mt_tr.sqlite` exists and never
opens or writes that database.

## Dependencies

Python standard library only. No pip packages are required.
