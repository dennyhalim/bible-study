# KJV + Strong's Obsidian Builder

Clean, dependency-free GitHub Actions builder for the KJV + Strong's reference
layer.

## Primary source

jsonBible:

https://jsonbible.org/

Documented tagged endpoint:

`https://jsonbible.org/v1/kjvstrongs/{book_id}/{chapter:03d}.json`

The builder uses the published 66-book chapter map and downloads exactly the
31,102 KJV verses. It does not use a nonexistent manifest endpoint.

## Output

```text
build/
├── build_report.json
├── source_manifest.json
├── raw/
└── obsidian-kjv/
    └── KJV/
        └── <Book>/<Chapter>/<Verse>.md
```

One Markdown note is generated per verse.

## CrossWire audit

Optional:

```bash
python scripts/import_kjv_strongs.py --crosswire-audit
```

CrossWire is **audit-only**. If GitLab/CrossWire is unavailable, the primary
jsonBible build still succeeds and the report records the audit as unavailable.

## SQLite separation

This builder refuses to run if `build/bible_mt_tr.sqlite` already exists and
never writes to it.

The KJV + Strong's layer is therefore kept separate from the MT/TR canonical
SQLite database.

## No pip dependencies

The importer uses Python standard-library modules plus Git, which is already
available on GitHub-hosted Ubuntu runners.
