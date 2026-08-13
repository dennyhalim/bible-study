# Fast Obsidian exporter

The Strong's export no longer performs one SQLite query per Strong's ID.

It uses one `json_each()` query to load all occurrences, groups them in Python,
and writes merged files containing up to 1,000 Strong's IDs each.

Default:

```bash
python scripts/export_obsidian.py
```

Change the batch size:

```bash
python scripts/export_obsidian.py --strongs-per-file 2000
```

The KJV remains one file per chapter. Strong's is merged into range files such as:

```text
Strong's/G0000-0999.md
Strong's/G1000-1999.md
Strong's/H0000-0999.md
```

Individual Strong's entries remain headings, so links can target `#G1234`.
