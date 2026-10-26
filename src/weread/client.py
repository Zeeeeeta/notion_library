"""WeRead Agent Gateway client."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from config import FINISHED_ARCHIVE_NAME, SKILL_VERSION, WEREAD_GATEWAY


@dataclass
class WeReadBook:
    book_id: str
    title: str
    author: str = ""
    cover: str = ""
    category: str = ""
    finish_reading: bool = False
    read_update_time: int = 0


@dataclass
class Highlight:
    mark_text: str
    chapter_uid: int | None = None
    chapter_title: str = ""
    create_time: int = 0
    color_style: int = 0
    range: str = ""


@dataclass
class ReviewNote:
    content: str
    abstract: str = ""
    chapter_title: str = ""
    create_time: int = 0
    review_type: int = 0


# type 4 is a starred book review; type 6 is a whole-book review.
BOOK_REVIEW_TYPES = {4, 6}


@dataclass
class BookmarkBundle:
    highlights: list[Highlight] = field(default_factory=list)
    reviews: list[ReviewNote] = field(default_factory=list)

    def book_review_text(self) -> str:
        parts = [
            review.content.strip()
            for review in self.reviews
            if review.review_type in BOOK_REVIEW_TYPES and review.content.strip()
        ]
        return "\n\n".join(parts)

    def margin_notes(self) -> list[ReviewNote]:
        return [review for review in self.reviews if review.review_type not in BOOK_REVIEW_TYPES]


class WeReadError(RuntimeError):
    pass


class WeReadClient:
    def __init__(self, api_key: str, skill_version: str = SKILL_VERSION) -> None:
        self.api_key = api_key
        self.skill_version = skill_version
        self._client = httpx.Client(timeout=60.0)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> WeReadClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def gateway(self, api_name: str, **params: Any) -> dict[str, Any]:
        body = {"api_name": api_name, "skill_version": self.skill_version, **params}
        resp = self._client.post(
            WEREAD_GATEWAY,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and data.get("upgrade_info"):
            msg = data["upgrade_info"].get("message") or str(data["upgrade_info"])
            raise WeReadError(f"WeRead skill upgrade required: {msg}")
        errcode = data.get("errcode") if isinstance(data, dict) else None
        if errcode not in (None, 0):
            raise WeReadError(
                f"WeRead API error for {api_name}: errcode={errcode} "
                f"errmsg={data.get('errmsg') or data}"
            )
        return data

    def shelf_sync(self) -> dict[str, Any]:
        return self.gateway("/shelf/sync")

    def book_info(self, book_id: str) -> dict[str, Any]:
        return self.gateway("/book/info", bookId=book_id)

    def bookmark_list(self, book_id: str) -> dict[str, Any]:
        return self.gateway("/book/bookmarklist", bookId=book_id)

    def my_reviews(self, book_id: str) -> list[dict[str, Any]]:
        reviews: list[dict[str, Any]] = []
        synckey = 0
        while True:
            data = self.gateway(
                "/review/list/mine",
                bookid=book_id,
                synckey=synckey,
                count=50,
            )
            batch = data.get("reviews") or []
            reviews.extend(batch)
            if not data.get("hasMore"):
                break
            synckey = data.get("synckey") or 0
            if not batch:
                break
        return reviews

    def finished_books(self, archive_name: str = FINISHED_ARCHIVE_NAME) -> list[WeReadBook]:
        shelf = self.shelf_sync()
        books_by_id: dict[str, dict[str, Any]] = {
            b["bookId"]: b for b in (shelf.get("books") or []) if b.get("bookId")
        }

        finished_ids: set[str] = set()
        for archive in shelf.get("archive") or []:
            name = (archive.get("name") or "").strip()
            if name == archive_name:
                finished_ids.update(archive.get("bookIds") or [])

        # Fallback: finishReading flag
        for book in books_by_id.values():
            if book.get("finishReading") in (1, True):
                finished_ids.add(book["bookId"])

        result: list[WeReadBook] = []
        for book_id in finished_ids:
            raw = books_by_id.get(book_id)
            if raw is None:
                # Book only referenced in archive — fetch info
                try:
                    info = self.book_info(book_id)
                    raw = info.get("book") or info
                except WeReadError:
                    continue
            result.append(self._parse_book(raw, book_id))

        result.sort(key=lambda b: b.read_update_time, reverse=True)
        return result

    def enrich_book(self, book: WeReadBook) -> WeReadBook:
        """Fill missing category/cover from /book/info when needed."""
        if book.category and book.cover and book.author:
            return book
        try:
            info = self.book_info(book.book_id)
            raw = info.get("book") or info
        except WeReadError:
            return book
        enriched = self._parse_book(raw, book.book_id)
        return WeReadBook(
            book_id=book.book_id,
            title=book.title or enriched.title,
            author=book.author or enriched.author,
            cover=book.cover or enriched.cover,
            category=book.category or enriched.category,
            finish_reading=True,
            read_update_time=book.read_update_time or enriched.read_update_time,
        )

    def get_notes(self, book_id: str) -> BookmarkBundle:
        data = self.bookmark_list(book_id)
        chapters = {
            c.get("chapterUid"): c.get("title") or ""
            for c in (data.get("chapters") or [])
            if c.get("chapterUid") is not None
        }
        highlights: list[Highlight] = []
        for item in data.get("updated") or []:
            if item.get("type") not in (None, 1):
                continue
            text = (item.get("markText") or "").strip()
            if not text:
                continue
            uid = item.get("chapterUid")
            highlights.append(
                Highlight(
                    mark_text=text,
                    chapter_uid=uid,
                    chapter_title=chapters.get(uid, "") if uid is not None else "",
                    create_time=int(item.get("createTime") or 0),
                    color_style=int(item.get("colorStyle") or 0),
                    range=str(item.get("range") or ""),
                )
            )

        # Sort by chapter then create time
        highlights.sort(key=lambda h: (h.chapter_uid or 0, h.create_time))

        reviews: list[ReviewNote] = []
        for wrapper in self.my_reviews(book_id):
            review = wrapper.get("review") or wrapper
            content = (review.get("content") or "").strip()
            if not content:
                continue
            reviews.append(
                ReviewNote(
                    content=content,
                    abstract=(review.get("abstract") or "").strip(),
                    chapter_title=(review.get("chapterName") or "").strip(),
                    create_time=int(review.get("createTime") or 0),
                    review_type=int(review.get("type") or 0),
                )
            )
        reviews.sort(key=lambda r: r.create_time)

        return BookmarkBundle(highlights=highlights, reviews=reviews)

    @staticmethod
    def _parse_book(raw: dict[str, Any], book_id: str | None = None) -> WeReadBook:
        category = ""
        cat = raw.get("category") or raw.get("newRatingDetail")
        if isinstance(cat, str):
            category = cat
        elif isinstance(cat, dict):
            category = cat.get("title") or ""
        # category sometimes nested as list of objects
        if not category and isinstance(raw.get("categories"), list):
            titles = []
            for c in raw["categories"]:
                if isinstance(c, dict) and c.get("title"):
                    titles.append(c["title"])
                elif isinstance(c, str):
                    titles.append(c)
            category = titles[0] if titles else ""

        return WeReadBook(
            book_id=str(book_id or raw.get("bookId") or ""),
            title=(raw.get("title") or "").strip(),
            author=(raw.get("author") or "").strip(),
            cover=(raw.get("cover") or "").strip(),
            category=category.strip(),
            finish_reading=raw.get("finishReading") in (1, True),
            read_update_time=int(raw.get("readUpdateTime") or raw.get("updateTime") or 0),
        )
