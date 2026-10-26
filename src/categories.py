"""Map WeRead categories onto the tags already used in Ziki."""

from __future__ import annotations

# More specific keys must come before broader ones.
# Learned from the current library: 纪实/传记/社会文化 are Non-Fic even when
# WeRead also files them under 文学 or 小说.
_TAG_RULES: tuple[tuple[str, str], ...] = (
    ("纪实", "Non-Fic"),
    ("传记", "Non-Fic"),
    ("社会文化", "Non-Fic"),
    ("历史", "History"),
    ("哲学", "Philosophy"),
    ("宗教", "Philosophy"),
    ("健康", "Health"),
    ("医学", "Health"),
    ("体育", "Health"),
    ("个人成长", "Brain"),
    ("经济理财", "Brain"),
    ("心理", "Brain"),
    ("文学", "Fiction"),
    ("小说", "Fiction"),
)

TAG_ORDER: tuple[str, ...] = (
    "Fiction",
    "Non-Fic",
    "Philosophy",
    "Health",
    "Brain",
    "History",
)
UNCATEGORIZED = "未分类"


def tag_for_category(category: str) -> str | None:
    text = category or ""
    for keyword, tag in _TAG_RULES:
        if keyword in text:
            return tag
    return None
