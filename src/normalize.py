"""Normalize book titles/authors for fuzzy matching."""

from __future__ import annotations

import re
import unicodedata

# Common noise in Chinese ebook titles
_SUFFIX_RE = re.compile(
    r"(（[^）]*）|\([^)]*\)|【[^】]*】|\[[^\]]*\]|全集|全本|完结|修订版|典藏版|精装版)+$"
)
_TRAILING_PAREN_RE = re.compile(r"\s*[（(][^）)]*[）)]\s*$")
_PUNCT_RE = re.compile(r"[\s\W_]+", re.UNICODE)


def _to_halfwidth(text: str) -> str:
    chars: list[str] = []
    for ch in text:
        code = ord(ch)
        if code == 0x3000:
            chars.append(" ")
        elif 0xFF01 <= code <= 0xFF5E:
            chars.append(chr(code - 0xFEE0))
        else:
            chars.append(ch)
    return "".join(chars)


def display_title(title: str) -> str:
    """Page title: drop trailing parenthetical notes such as （微信读书特别版）."""
    if not title:
        return ""
    text = title.strip()
    previous = None
    while previous != text:
        previous = text
        text = _TRAILING_PAREN_RE.sub("", text).strip()
    return text


def normalize_title(title: str) -> str:
    if not title:
        return ""
    text = display_title(title)
    text = _to_halfwidth(text).lower()
    # Strip repeated trailing noise
    prev = None
    while prev != text:
        prev = text
        text = _SUFFIX_RE.sub("", text).strip()
    text = _PUNCT_RE.sub("", text)
    return text


def normalize_author(author: str) -> str:
    if not author:
        return ""
    text = unicodedata.normalize("NFKC", author.strip())
    text = _to_halfwidth(text).lower()
    text = text.replace("著", "").replace("编", "")
    text = _PUNCT_RE.sub("", text)
    return text


def titles_match(a: str, b: str) -> bool:
    na, nb = normalize_title(a), normalize_title(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    # One contains the other (handles truncated Notion titles)
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    return len(shorter) >= 4 and shorter in longer


def authors_match(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return True  # author optional for matching
    na, nb = normalize_author(a), normalize_author(b)
    if not na or not nb:
        return True
    if na == nb:
        return True
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    return len(shorter) >= 2 and shorter in longer
