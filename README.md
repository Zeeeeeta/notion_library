# WeRead → Notion finished-book sync

When you finish a book in 微信读书 (move it to the **读完** folder), this tool finds books that are not yet in your existing Notion reading database and creates a page for each one:

1. **Category tag** from WeRead (when your DB has a matching property)
2. Top **callout** left for your 读后感 / journal
3. All personal **划线** (and 想法) underneath, grouped by chapter

It never overwrites existing Notion pages.

> Notion’s API cannot drag pages into the left Favorites sidebar. After sync, add Favorites by category yourself if you still want that layout.

## Setup (once)

### 1. WeRead API Key

1. Open [微信读书 Skills](https://weread.qq.com/r/weread-skills)
2. Sign in → create / copy your API Key (`wrk-…`)

### 2. Notion integration

1. Create an [Internal Integration](https://www.notion.so/my-integrations)
2. Copy the secret (`secret_…` or `ntn_…`)
3. Open your reading database → **⋯** → **Connections** → add the integration

Database id (already the default): `4a61a181aa6541da89b7ad9ce6316f33`

### 3. Install

```bash
cd notion_library
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
# edit .env with WEREAD_API_KEY and NOTION_TOKEN
```

## Usage

```bash
# Dry-run: what would be created?
weread-sync check

# Create missing pages
weread-sync apply

# One book only
weread-sync check --book "三体"
weread-sync apply --book "三体" -y
```

Or without the console script:

```bash
PYTHONPATH=src python -m sync check
PYTHONPATH=src python -m sync apply -y
```

## Cursor agent

A project skill lives at [`.cursor/skills/weread-notion-sync/SKILL.md`](.cursor/skills/weread-notion-sync/SKILL.md). When you ask to sync finished books, the agent should run `weread-sync check` then `weread-sync apply -y`.

## Matching

Finished books come from the shelf archive named **读完**, with a fallback to `finishReading == 1`. Existing Notion rows are matched by normalized title (+ author when present), and by `WeRead BookId` if that property exists (the tool will try to add it once).
