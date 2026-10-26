from categories import tag_for_category
from normalize import authors_match, display_title, normalize_title, titles_match
from notion.page_builder import page_title


def test_weread_category_maps_to_existing_tags():
    assert tag_for_category("文学-外国文学") == "Fiction"
    assert tag_for_category("社会文化-社科") == "Non-Fic"
    assert tag_for_category("文学-纪实文学") == "Non-Fic"
    assert tag_for_category("哲学宗教-西方哲学") == "Philosophy"
    assert tag_for_category("医学健康-健康") == "Health"
    assert tag_for_category("个人成长-人生哲学") == "Brain"
    assert tag_for_category("待评分") is None


def test_display_title_drops_trailing_parentheses():
    assert display_title("什么是权力（微信读书特别版）") == "什么是权力"
    assert display_title("什么是权力 (特别版)") == "什么是权力"
    assert display_title("伊豆舞女") == "伊豆舞女"
    assert display_title("我们为什么吃（太多）：食欲的新科学") == "我们为什么吃（太多）：食欲的新科学"


def test_normalize_strips_suffix():
    assert normalize_title("三体全集（全三册）") == normalize_title("三体")


def test_titles_match_fuzzy():
    assert titles_match("Harry Potter and the Sorcerer's Stone", "Harry Potter and the Sorcerers Stone")
    assert titles_match("置身事内", "置身事内：中国政府与经济发展")


def test_page_title_marks_missing_review():
    assert page_title("什么是权力（微信读书特别版）", "") == "什么是权力(TO-DO)"
    assert page_title("伊豆舞女", "好安静的故事") == "伊豆舞女"
    assert page_title("伊豆舞女(TO-DO)", "好安静的故事") == "伊豆舞女(TO-DO)"


def test_authors_optional():
    assert authors_match("刘慈欣", "")
    assert authors_match("刘慈欣 著", "刘慈欣")
