# Validator fix

This replaces the stale validator that expected 67 Markdown files in the
NotebookLM directory.

Current contract:

- SQLite: 66 books, non-empty verses and words, integrity check `ok`
- Obsidian: 1189 chapter Markdown files + merged Strong's files
- Gemini/NotebookLM: 66 book Markdown files + merged Strong's files

Strong's files are intentionally not counted as 67. Their number depends on
the configured batch size.
