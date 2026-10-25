---
name: weread-notion-sync
description: >-
  Sync finished 微信读书 (WeRead) books into the user's existing Notion reading
  database. Use when the user asks to sync books, check which finished books
  need Notion pages, create book pages from WeRead, or starts this reading-sync
  agent workflow.
---

# WeRead → Notion finished-book sync

## When to use

Apply this skill when the user wants to:

- Sync finished books from 微信读书 to Notion
- Check which 读完 books are missing Notion pages
- Create Notion book pages with 划线 and a 读后感 callout

## Workflow

Project root: the repo that contains `weread-sync` / `src/sync.py`.

1. Ensure `.env` exists with `WEREAD_API_KEY`, `NOTION_TOKEN`, and `NOTION_DATABASE_ID` (see `.env.example`). If missing, tell the user how to create keys — do not invent secrets.
2. Prefer the installed CLI; otherwise use `PYTHONPATH=src python -m sync`.
3. Always run a dry-run first:

```bash
source .venv/bin/activate 2>/dev/null; weread-sync check
# or: PYTHONPATH=src python -m sync check
```

4. Show the user the missing-book list from the command output.
5. Unless the user asked for dry-run / check only, create pages:

```bash
weread-sync apply -y
# or: PYTHONPATH=src python -m sync apply -y
```

6. Report created page URLs and remind them: Notion API cannot add Favorites to the left sidebar — they may still drag new pages into category Favorites manually.

## Rules

- Only sync books in the WeRead **读完** archive (fallback: `finishReading`).
- Never overwrite or delete existing Notion pages.
- Do not commit `.env` or API keys.
- One book only when the user names a title: `weread-sync apply --book "书名" -y`.

## Page shape (already implemented by the CLI)

- Category/tag property filled from WeRead when the DB has a matching property
- Top callout for 读后感 / journal (empty for the user to fill)
- 划线 grouped by chapter; 想法 section when present
