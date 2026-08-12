# KJV + Strong's — committed-source importer

## Canonical source file

The eBible.org archive contains several XML files. The Bible text source is
specifically:

```text
eng-kjv2006_usfx.xml
```

It is stored in this repository at:

```text
vendor/kjv2006/eng-kjv2006_usfx.xml
```

Source archive:

https://ebible.org/Scriptures/eng-kjv2006_usfx.zip

Source page:

https://ebible.org/find/show.php?id=eng-kjv2006

## Reliability model

The repository keeps a known-good copy of the source XML.

Normal CI:

```text
committed XML
    ↓
validate
    ↓
build
```

Manual refresh:

```text
download archive
    ↓
extract eng-kjv2006_usfx.xml
    ↓
validate 66 / 31,102
    ↓
replace committed XML
    ↓
commit + push
```

If the downloader fails during `--refresh`, the existing committed XML is
used automatically. A refresh is never accepted unless the downloaded file
passes validation.

This means a temporary eBible outage cannot break the normal build.

## Important GitHub Actions permission

The workflow uses `contents: write` only for the explicit `refresh_source`
manual action because that action commits a validated source update.

Scheduled and normal builds do not modify the repository.

## Output

```text
build/
├── build_report.json
├── source_manifest.json
└── obsidian-kjv/
    └── KJV/
        └── Book/Chapter/Verse.md
```

## SQLite separation

`build/bible_mt_tr.sqlite` is never opened, created, or modified.

## Dependencies

Python standard library only.
