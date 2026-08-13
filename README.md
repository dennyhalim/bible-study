# KJV + Strong's importer

Uses eBible.org KJV2006 USFX, specifically `eng-kjv2006_usfx.xml`.

The important fix is USFX parsing: `<v>` is a verse-start milestone, not a
verse container. The parser keeps the active verse while traversing the tree
and reads Strong's values from `<w>` attributes.

Validation requires 66 books, 31,102 verses, word records, and non-zero
Strong's tags.

The source is committed at `vendor/kjv2006/eng-kjv2006_usfx.xml`. Normal
builds use it. `refresh_source=true` downloads, validates, and commits a
replacement. Failed refreshes fall back to the committed source.

The importer never creates or modifies `build/bible_mt_tr.sqlite`.

Source archive: https://ebible.org/Scriptures/eng-kjv2006_usfx.zip
