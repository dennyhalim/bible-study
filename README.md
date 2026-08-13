# Bible Study committed-data pipeline

`data/bible_mt_tr.sqlite` is the committed, last-known-good SQLite snapshot.

The GitHub Actions workflow:

1. preserves the previous database;
2. optionally refreshes the committed source;
3. builds a new SQLite database in `build/`;
4. validates it;
5. only then copies it to `data/bible_mt_tr.sqlite`;
6. commits the validated database and refreshed source.

A failed download does **not** delete the previous source.

A failed SQLite build does **not** replace the committed database.

The source expected by the importer is:

`vendor/kjv2006/eng-kjv2006_usfx.xml`

Do not fabricate or substitute another KJV XML filename.

The schema reserves `lemma` and `morphology` for verified TR/MT imports; empty values are preferable to invented lexical data.
