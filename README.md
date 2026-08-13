# Fast Gemini / NotebookLM exporter

The exporter performs one bulk SQLite query for all Strong's occurrences,
then groups the data in Python.

Default output:

```text
build/notebooklm/
├── Genesis.md
├── Exodus.md
├── ...
├── Revelation.md
└── Strongs/
    ├── G0000-1999.md
    ├── G2000-3999.md
    ├── G4000-5999.md
    └── H0000-9999.md
```

Run:

```bash
python scripts/export_notebooklm.py
```

Change the Strong's batch size:

```bash
python scripts/export_notebooklm.py --strongs-per-file 5000
```

Book files remain separate because they are better retrieval units for
Gemini/NotebookLM than one enormous Markdown source.
