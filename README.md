# KJV + Strong's Obsidian Adapter

This adapter adds the KJV + Strong's reference layer to the Obsidian build.

## Source

Primary: jsonBible `kjvstrongs`.

Secondary: CrossWire KJV OSIS, optionally downloaded for independent audit.

jsonBible documents the tagged endpoint as:

`https://jsonbible.org/v1/kjvstrongs/{book}/{chapter}.json`

The tagged records contain the reading text and ordered word arrays with Strong's
numbers.

## SQLite policy

This adapter does **not** write KJV data into `bible_mt_tr.sqlite`.

KJV remains an Obsidian-only reference layer.

## Run locally

```bash
python scripts/import_kjv_strongs.py --download-crosswire
python tests/test_kjv.py
```

## GitHub Actions

The workflow builds the vault, validates it, and uploads:

- `kjv-strongs-obsidian.zip`
- `build_report.json`
- `source_manifest.json`
- `SHA256SUMS`

The workflow does not modify the canonical MT/TR SQLite database.
