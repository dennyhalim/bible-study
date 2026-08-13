# Cloudflare D1 deployment

This adds Cloudflare D1 as an online read/query copy of the canonical SQLite corpus.

## Architecture

```text
data/bible_mt_tr.sqlite
        |
        +--> local SQLite / Obsidian / Gemini
        |
        +--> scripts/export_d1.py
                    |
                    v
             build/d1/bible_mt_tr.sql
                    |
                    v
             Cloudflare D1
```

The SQLite file remains canonical. D1 is a deployed copy.

## First-time setup

Create a D1 database:

```bash
npx wrangler@latest d1 create bible-mt-tr
```

Cloudflare returns the database ID.

Set a GitHub repository variable:

```text
D1_DATABASE_NAME=bible-mt-tr
```

Set these GitHub repository secrets:

```text
CLOUDFLARE_API_TOKEN
CLOUDFLARE_ACCOUNT_ID
```

The API token should have the minimum D1 permissions required for the deployment.

## Manual local import

After generating the SQL:

```bash
python scripts/export_d1.py
python scripts/validate_d1.py
npx wrangler d1 execute bible-mt-tr --remote --file=build/d1/bible_mt_tr.sql --yes
```

Cloudflare documents this SQLite-to-SQL-to-D1 import flow. A raw SQLite file is not uploaded directly; it is converted to SQL first. The documented D1 import path uses `wrangler d1 execute --remote --file`. 

## Important

The deployment workflow currently replaces/inserts the generated corpus into the remote database using the generated SQL dump. For a production public API, use a staging D1 database first and add an explicit migration/versioning strategy before making automated destructive updates.

The canonical repository database is never dependent on D1 being available.
