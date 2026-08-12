# Bible MT/TR Build Pipeline

Produces:

- `build/bible_mt_tr.sqlite` — canonical MT/TR lexical/morphological database
- `build/obsidian-vault/` — derived Obsidian vault
- `build/build_report.json`
- `build/source_manifest.json`
- `build/SHA256SUMS`

## KJV policy

KJV is **not imported into SQLite**.

KJV + Strong's belongs only in the generated Obsidian layer. The pipeline refuses
to invent Strong's tags. A verified machine-readable KJV+Strong's dataset must be
configured before the KJV adapter is enabled.

## GitHub Actions

The workflow runs manually, on source-code changes, and monthly.

It validates the SQLite database and uploads the database, vault ZIP, report,
manifest and checksums as workflow artifacts.

## Next adapter layer

The repository structure intentionally separates source adapters from the schema.
Pin exact STEPBible/Open Scriptures files and add format-specific parsers for:

- TAGNT/TR
- TAHOT/WLC
- TBESG
- TBESH
- TFLSJ
- TEGMC
- TEHMC
- Open Scriptures BDB/Strong's

Do not substitute a different Greek NT or Hebrew text without recording it as a
different edition/source.
