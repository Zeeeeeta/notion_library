"""Notion API helpers: schema, query, create."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from config import NOTION_VERSION, ROOT
from normalize import authors_match, normalize_title, titles_match


@dataclass
class NotionBookRow:
    page_id: str
    title: str
    author: str = ""
    book_id: str = ""
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class PropertyRef:
    name: str
    type: str
    id: str = ""


@dataclass
class SchemaInfo:
    database_id: str
    title_prop: PropertyRef
    author_prop: PropertyRef | None = None
    category_prop: PropertyRef | None = None
    cover_prop: PropertyRef | None = None
    book_id_prop: PropertyRef | None = None
    all_properties: dict[str, dict[str, Any]] = field(default_factory=dict)
    sample_callout: dict[str, Any] | None = None


class NotionError(RuntimeError):
    pass


_TITLE_NAMES = {"name", "title", "书名", "书籍", "书", "book", "book title"}
_AUTHOR_NAMES = {"author", "作者", "著者"}
_CATEGORY_NAMES = {
    "category",
    "categories",
    "tag",
    "tags",
    "分类",
    "类别",
    "标签",
    "类型",
}
_COVER_NAMES = {"cover", "封面", "cover url", "封面链接"}
_BOOK_ID_NAMES = {"weread bookid", "weread book id", "bookid", "book id", "微信读书id"}


class NotionClient:
    def __init__(self, token: str, database_id: str) -> None:
        self.token = token
        self.database_id = database_id
        self._client = httpx.Client(
            base_url="https://api.notion.com/v1",
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )
        self._cache_path = ROOT / ".cache" / "schema_cache.json"

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> NotionClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        resp = self._client.request(method, path, **kwargs)
        if resp.status_code >= 400:
            raise NotionError(f"Notion {method} {path}: {resp.status_code} {resp.text}")
        return resp.json()

    def get_database(self) -> dict[str, Any]:
        return self._request("GET", f"/databases/{self.database_id}")

    def introspect_schema(self, use_cache: bool = True) -> SchemaInfo:
        if use_cache and self._cache_path.exists():
            try:
                cached = json.loads(self._cache_path.read_text(encoding="utf-8"))
                if cached.get("database_id") == self.database_id:
                    return self._schema_from_dict(cached)
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

        db = self.get_database()
        props = db.get("properties") or {}
        title_prop = self._find_prop(props, _TITLE_NAMES, {"title"})
        if title_prop is None:
            # Every DB has exactly one title property
            for name, meta in props.items():
                if meta.get("type") == "title":
                    title_prop = PropertyRef(name=name, type="title", id=meta.get("id", ""))
                    break
        if title_prop is None:
            raise NotionError("Could not find a title property on the Notion database.")

        schema = SchemaInfo(
            database_id=self.database_id,
            title_prop=title_prop,
            author_prop=self._find_prop(props, _AUTHOR_NAMES, {"rich_text", "text"}),
            category_prop=self._find_prop(
                props, _CATEGORY_NAMES, {"multi_select", "select", "rich_text"}
            ),
            cover_prop=self._find_prop(props, _COVER_NAMES, {"url", "files", "rich_text"}),
            book_id_prop=self._find_prop(props, _BOOK_ID_NAMES, {"rich_text", "text"}),
            all_properties=props,
        )

        # Sample first page for callout style
        pages = self.query_all_pages(page_size=5)
        for page in pages[:3]:
            callout = self._find_first_callout(page["id"])
            if callout:
                schema.sample_callout = callout
                break

        self._save_schema_cache(schema)
        return schema

    def ensure_book_id_property(self, schema: SchemaInfo) -> SchemaInfo:
        """Add a WeRead BookId rich_text property when missing and writable."""
        if schema.book_id_prop is not None:
            return schema
        try:
            updated = self._request(
                "PATCH",
                f"/databases/{self.database_id}",
                json={
                    "properties": {
                        "WeRead BookId": {"rich_text": {}},
                    }
                },
            )
        except NotionError:
            return schema

        props = updated.get("properties") or schema.all_properties
        book_id = self._find_prop(props, _BOOK_ID_NAMES | {"weread bookid"}, {"rich_text"})
        if book_id is None and "WeRead BookId" in props:
            meta = props["WeRead BookId"]
            book_id = PropertyRef(
                name="WeRead BookId",
                type=meta.get("type", "rich_text"),
                id=meta.get("id", ""),
            )
        schema.book_id_prop = book_id
        schema.all_properties = props
        self._save_schema_cache(schema)
        return schema

    def query_all_pages(self, page_size: int = 100) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            body: dict[str, Any] = {"page_size": page_size}
            if cursor:
                body["start_cursor"] = cursor
            data = self._request("POST", f"/databases/{self.database_id}/query", json=body)
            results.extend(data.get("results") or [])
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
        return results

    def list_existing_books(self, schema: SchemaInfo) -> list[NotionBookRow]:
        rows: list[NotionBookRow] = []
        for page in self.query_all_pages():
            props = page.get("properties") or {}
            title = self._plain_title(props.get(schema.title_prop.name))
            author = ""
            if schema.author_prop:
                author = self._plain_rich_text(props.get(schema.author_prop.name))
            book_id = ""
            if schema.book_id_prop:
                book_id = self._plain_rich_text(props.get(schema.book_id_prop.name))
            rows.append(
                NotionBookRow(
                    page_id=page["id"],
                    title=title,
                    author=author,
                    book_id=book_id,
                    properties=props,
                )
            )
        return rows

    def find_match(
        self,
        existing: list[NotionBookRow],
        title: str,
        author: str = "",
        book_id: str = "",
    ) -> NotionBookRow | None:
        if book_id:
            for row in existing:
                if row.book_id and row.book_id == book_id:
                    return row
        for row in existing:
            if titles_match(row.title, title) and authors_match(row.author, author):
                return row
        # Title-only fallback with normalized equality
        nt = normalize_title(title)
        for row in existing:
            if normalize_title(row.title) == nt:
                return row
        return None

    def get_block_children(self, block_id: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"page_size": 100}
            if cursor:
                params["start_cursor"] = cursor
            data = self._request("GET", f"/blocks/{block_id}/children", params=params)
            results.extend(data.get("results") or [])
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
        return results

    def create_page(
        self,
        properties: dict[str, Any],
        children: list[dict[str, Any]],
        cover_url: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "parent": {"database_id": self.database_id},
            "properties": properties,
        }
        if cover_url:
            body["cover"] = {"type": "external", "external": {"url": cover_url}}
        # Notion limits children on create to 100
        first, rest = children[:100], children[100:]
        if first:
            body["children"] = first
        page = self._request("POST", "/pages", json=body)
        page_id = page["id"]
        for i in range(0, len(rest), 100):
            chunk = rest[i : i + 100]
            self._request(
                "PATCH",
                f"/blocks/{page_id}/children",
                json={"children": chunk},
            )
        return page

    def _find_first_callout(self, page_id: str) -> dict[str, Any] | None:
        try:
            blocks = self.get_block_children(page_id)
        except NotionError:
            return None
        for block in blocks:
            if block.get("type") == "callout":
                callout = block.get("callout") or {}
                return {
                    "icon": callout.get("icon"),
                    "color": callout.get("color") or "gray_background",
                    "rich_text": callout.get("rich_text") or [],
                }
        return None

    def _save_schema_cache(self, schema: SchemaInfo) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "database_id": schema.database_id,
            "title_prop": schema.title_prop.__dict__,
            "author_prop": schema.author_prop.__dict__ if schema.author_prop else None,
            "category_prop": schema.category_prop.__dict__ if schema.category_prop else None,
            "cover_prop": schema.cover_prop.__dict__ if schema.cover_prop else None,
            "book_id_prop": schema.book_id_prop.__dict__ if schema.book_id_prop else None,
            "sample_callout": schema.sample_callout,
            "property_names": list(schema.all_properties.keys()),
        }
        self._cache_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @staticmethod
    def _schema_from_dict(data: dict[str, Any]) -> SchemaInfo:
        def ref(obj: dict[str, Any] | None) -> PropertyRef | None:
            if not obj:
                return None
            return PropertyRef(**obj)

        title = ref(data.get("title_prop"))
        if title is None:
            raise NotionError("Invalid schema cache: missing title_prop")
        return SchemaInfo(
            database_id=data["database_id"],
            title_prop=title,
            author_prop=ref(data.get("author_prop")),
            category_prop=ref(data.get("category_prop")),
            cover_prop=ref(data.get("cover_prop")),
            book_id_prop=ref(data.get("book_id_prop")),
            sample_callout=data.get("sample_callout"),
        )

    @staticmethod
    def _find_prop(
        props: dict[str, Any],
        names: set[str],
        allowed_types: set[str],
    ) -> PropertyRef | None:
        # Exact / case-insensitive name match preferred
        lowered = {k.lower(): k for k in props}
        for name in names:
            key = lowered.get(name.lower())
            if key and props[key].get("type") in allowed_types:
                meta = props[key]
                return PropertyRef(name=key, type=meta["type"], id=meta.get("id", ""))
        # Fallback: first property of allowed type whose name contains a keyword
        for key, meta in props.items():
            if meta.get("type") not in allowed_types:
                continue
            lk = key.lower()
            if any(n in lk for n in names):
                return PropertyRef(name=key, type=meta["type"], id=meta.get("id", ""))
        return None

    @staticmethod
    def _plain_title(prop: dict[str, Any] | None) -> str:
        if not prop:
            return ""
        items = prop.get("title") or []
        return "".join(t.get("plain_text") or "" for t in items).strip()

    @staticmethod
    def _plain_rich_text(prop: dict[str, Any] | None) -> str:
        if not prop:
            return ""
        key = prop.get("type")
        items = prop.get(key) if key in ("rich_text", "title") else prop.get("rich_text")
        if not items:
            return ""
        return "".join(t.get("plain_text") or "" for t in items).strip()
