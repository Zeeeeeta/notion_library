"""Build Notion page properties and body blocks for a finished book."""

from __future__ import annotations

from typing import Any

from categories import tag_for_category
from normalize import display_title
from notion.client import SchemaInfo
from weread.client import BookmarkBundle, WeReadBook


def _rich_text(content: str, bold: bool = False) -> list[dict[str, Any]]:
    if not content:
        return []
    # Notion rich text items max 2000 chars
    chunks: list[dict[str, Any]] = []
    for i in range(0, len(content), 2000):
        part = content[i : i + 2000]
        item: dict[str, Any] = {
            "type": "text",
            "text": {"content": part},
        }
        if bold:
            item["annotations"] = {"bold": True}
        chunks.append(item)
    return chunks


def _heading_2(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": _rich_text(text)},
    }


def _heading_3(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "heading_3",
        "heading_3": {"rich_text": _rich_text(text)},
    }


def _quote(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "quote",
        "quote": {"rich_text": _rich_text(text)},
    }


def _paragraph(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": _rich_text(text)},
    }


def _divider() -> dict[str, Any]:
    return {"object": "block", "type": "divider", "divider": {}}


def page_title(title: str, review_text: str) -> str:
    """Use the cleaned title, or append (TO-DO) when WeRead has no book review."""
    cleaned = display_title(title)
    if review_text.strip() or cleaned.endswith("(TO-DO)"):
        return cleaned
    return f"{cleaned}(TO-DO)"


class PageBuilder:
    def __init__(self, schema: SchemaInfo) -> None:
        self.schema = schema

    def build_properties(self, book: WeReadBook, notes: BookmarkBundle) -> dict[str, Any]:
        props: dict[str, Any] = {
            self.schema.title_prop.name: {
                "title": _rich_text(page_title(book.title, notes.book_review_text())),
            }
        }

        if self.schema.author_prop and book.author:
            props[self.schema.author_prop.name] = self._set_by_type(
                self.schema.author_prop.type, book.author
            )

        if self.schema.category_prop:
            tag = tag_for_category(book.category)
            if tag:
                props[self.schema.category_prop.name] = self._set_by_type(
                    self.schema.category_prop.type, tag
                )

        if self.schema.cover_prop and book.cover:
            props[self.schema.cover_prop.name] = self._set_cover(
                self.schema.cover_prop.type, book.cover
            )

        if self.schema.book_id_prop and book.book_id:
            props[self.schema.book_id_prop.name] = self._set_by_type(
                self.schema.book_id_prop.type, book.book_id
            )

        return props

    def build_children(self, notes: BookmarkBundle) -> list[dict[str, Any]]:
        children: list[dict[str, Any]] = [
            self._review_callout(notes.book_review_text()),
            _divider(),
            _heading_2("划线"),
        ]

        if not notes.highlights:
            children.append(_paragraph("（暂无划线）"))
        else:
            current_chapter: str | None = None
            for h in notes.highlights:
                chapter = h.chapter_title or "未分章"
                if chapter != current_chapter:
                    current_chapter = chapter
                    children.append(_heading_3(chapter))
                children.append(_quote(h.mark_text))

        margin_notes = notes.margin_notes()
        if margin_notes:
            children.append(_divider())
            children.append(_heading_2("想法"))
            for r in margin_notes:
                if r.abstract:
                    children.append(_quote(r.abstract))
                label = r.chapter_title
                text = r.content if not label else f"[{label}] {r.content}"
                children.append(_paragraph(text))

        return children

    def _review_callout(self, review_text: str = "") -> dict[str, Any]:
        sample = self.schema.sample_callout or {}
        icon = sample.get("icon") or {"type": "emoji", "emoji": "✍️"}
        color = sample.get("color") or "gray_background"

        prompt = review_text.strip()
        if not prompt:
            prompt = "读后感"
            sample_texts = sample.get("rich_text") or []
            if sample_texts:
                plain = "".join(t.get("plain_text") or "" for t in sample_texts).strip()
                if plain and len(plain) <= 40:
                    prompt = plain.split("\n")[0].strip() or prompt

        return {
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": _rich_text(prompt),
                "icon": icon,
                "color": color,
            },
        }

    def _set_by_type(self, prop_type: str, value: str) -> dict[str, Any]:
        if prop_type in ("rich_text", "text"):
            return {"rich_text": _rich_text(value)}
        if prop_type == "title":
            return {"title": _rich_text(value)}
        if prop_type == "url":
            return {"url": value}
        if prop_type == "select":
            return {"select": {"name": value[:100]}}
        if prop_type == "multi_select":
            return {"multi_select": [{"name": value[:100]}]}
        return {"rich_text": _rich_text(value)}

    def _set_cover(self, prop_type: str, url: str) -> dict[str, Any]:
        if prop_type == "url":
            return {"url": url}
        if prop_type == "files":
            return {
                "files": [
                    {
                        "type": "external",
                        "name": "cover",
                        "external": {"url": url},
                    }
                ]
            }
        return {"rich_text": _rich_text(url)}
