"""CLI: check / apply finished WeRead books into Notion."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from config import load_settings
from normalize import display_title, titles_match
from notion.client import NotionClient, NotionBookRow, SchemaInfo
from notion.page_builder import PageBuilder
from weread.client import WeReadBook, WeReadClient


@dataclass
class MissingBook:
    book: WeReadBook
    reason: str = "not in Notion"


def find_missing(
    finished: list[WeReadBook],
    existing: list[NotionBookRow],
    notion: NotionClient,
) -> list[MissingBook]:
    missing: list[MissingBook] = []
    for book in finished:
        match = notion.find_match(
            existing,
            title=book.title,
            author=book.author,
            book_id=book.book_id,
        )
        if match is None:
            missing.append(MissingBook(book=book))
    return missing


def filter_by_title(books: list[WeReadBook], title: str) -> list[WeReadBook]:
    return [b for b in books if titles_match(b.title, title) or title in b.title]


def prepare(
    weread: WeReadClient,
    notion: NotionClient,
    book_filter: str | None = None,
) -> tuple[SchemaInfo, list[WeReadBook], list[MissingBook], list[NotionBookRow]]:
    schema = notion.introspect_schema()
    schema = notion.ensure_book_id_property(schema)

    finished = weread.finished_books()
    if book_filter:
        finished = filter_by_title(finished, book_filter)
        if not finished:
            print(f'No finished WeRead book matched --book "{book_filter}".')

    existing = notion.list_existing_books(schema)
    missing = find_missing(finished, existing, notion)
    return schema, finished, missing, existing


def cmd_check(book: str | None = None) -> int:
    settings = load_settings()
    with WeReadClient(settings.weread_api_key) as weread, NotionClient(
        settings.notion_token, settings.notion_database_id
    ) as notion:
        schema, finished, missing, existing = prepare(weread, notion, book)
        print(f"Notion database: {settings.notion_database_id}")
        print(f"Title property: {schema.title_prop.name}")
        if schema.category_prop:
            print(f"Category property: {schema.category_prop.name} ({schema.category_prop.type})")
        print(f"Existing Notion books: {len(existing)}")
        print(f"Finished on WeRead (读完 / finishReading): {len(finished)}")
        print()
        if not missing:
            print("All finished WeRead books already have Notion pages.")
            return 0
        print(f"{len(missing)} book(s) need a Notion page:\n")
        for i, item in enumerate(missing, 1):
            b = item.book
            cat = f"  [{b.category}]" if b.category else ""
            print(f"  {i}. {display_title(b.title)} — {b.author}{cat}")
            print(f"     bookId={b.book_id}")
        print("\nRun: weread-sync apply")
        return 0


def cmd_apply(book: str | None = None, yes: bool = False) -> int:
    settings = load_settings()
    with WeReadClient(settings.weread_api_key) as weread, NotionClient(
        settings.notion_token, settings.notion_database_id
    ) as notion:
        schema, _finished, missing, _existing = prepare(weread, notion, book)
        if not missing:
            print("Nothing to create — all finished books are already in Notion.")
            return 0

        print(f"Will create {len(missing)} page(s):")
        for item in missing:
            print(f"  - {display_title(item.book.title)}")
        if not yes:
            answer = input("Continue? [y/N] ").strip().lower()
            if answer not in ("y", "yes"):
                print("Aborted.")
                return 1

        builder = PageBuilder(schema)
        created = 0
        for item in missing:
            book_meta = weread.enrich_book(item.book)
            print(f"Creating: {display_title(book_meta.title)} ...", flush=True)
            notes = weread.get_notes(book_meta.book_id)
            properties = builder.build_properties(book_meta, notes)
            children = builder.build_children(notes)
            page = notion.create_page(
                properties=properties,
                children=children,
                cover_url=book_meta.cover or None,
            )
            url = page.get("url") or page.get("id")
            print(
                f"  OK — {len(notes.highlights)} highlights, "
                f"{len(notes.reviews)} reviews → {url}"
            )
            created += 1

        print(f"\nCreated {created} page(s).")
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="weread-sync",
        description="Sync finished WeRead (读完) books into your Notion reading database.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="List finished books missing from Notion")
    check.add_argument("--book", help="Only consider a book whose title matches")

    apply = sub.add_parser("apply", help="Create Notion pages for missing finished books")
    apply.add_argument("--book", help="Only create a page for this book title")
    apply.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip confirmation prompt (for agent / CI use)",
    )

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            raise SystemExit(cmd_check(book=args.book))
        if args.command == "apply":
            raise SystemExit(cmd_apply(book=args.book, yes=args.yes))
        parser.error(f"Unknown command: {args.command}")
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
