from normalize import authors_match, normalize_title, titles_match


def test_normalize_strips_suffix():
    assert normalize_title("三体全集（全三册）") == normalize_title("三体")


def test_titles_match_fuzzy():
    assert titles_match("Harry Potter and the Sorcerer's Stone", "Harry Potter and the Sorcerers Stone")
    assert titles_match("置身事内", "置身事内：中国政府与经济发展")


def test_authors_optional():
    assert authors_match("刘慈欣", "")
    assert authors_match("刘慈欣 著", "刘慈欣")
