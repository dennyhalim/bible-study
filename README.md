# Bible Study corpus pipeline

## Canonical data

`data/bible_mt_tr.sqlite` is the committed, last-known-good database.

`vendor/kjv2006/eng-kjv2006_usfx.xml` is the committed KJV2006 source fallback.

The workflow never promotes an unvalidated database.

## Outputs

- `data/bible_mt_tr.sqlite` — canonical committed SQLite
- `build/obsidian/` — chapter-level Obsidian vault plus Strong's notes
- `build/notebooklm/` — 66 book sources plus a Strong's occurrence index
- GitHub Actions artifacts contain SQLite + both exports

## Important

The importer does not invent lemma or morphology. Those fields are reserved for
the verified TR/MT lexical and morphology datasets.

Put your existing validated source files into:

`vendor/kjv2006/eng-kjv2006_usfx.xml`

and, if already available:

`data/bible_mt_tr.sqlite`

before the first workflow run.
