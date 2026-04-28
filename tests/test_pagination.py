from backend.pagination import offset, paginate


def test_short_pagination_shows_all_pages():
    pi = paginate(total=30, page=1, per_page=10)
    assert pi.total_pages == 3
    assert pi.pages == [1, 2, 3]
    assert pi.has_prev is False
    assert pi.has_next is True


def test_pagination_clamps_below_one():
    pi = paginate(total=30, page=0, per_page=10)
    assert pi.page == 1


def test_pagination_clamps_above_total():
    pi = paginate(total=30, page=999, per_page=10)
    assert pi.page == 3
    assert pi.has_next is False


def test_long_pagination_uses_ellipses_in_middle():
    pi = paginate(total=120, page=6, per_page=10)
    # 12 pages, current=6: expect [1, …, 5, 6, 7, …, 12]
    assert pi.pages == [1, None, 5, 6, 7, None, 12]


def test_long_pagination_near_start_omits_left_ellipsis():
    pi = paginate(total=120, page=2, per_page=10)
    # current=2: 1, 2, 3, …, 12 — no left ellipsis since pages are contiguous
    assert pi.pages == [1, 2, 3, None, 12]


def test_long_pagination_near_end_omits_right_ellipsis():
    pi = paginate(total=120, page=11, per_page=10)
    assert pi.pages == [1, None, 10, 11, 12]


def test_zero_total_still_returns_one_page():
    pi = paginate(total=0, page=1, per_page=10)
    assert pi.total_pages == 1
    assert pi.pages == [1]
    assert pi.has_prev is False
    assert pi.has_next is False


def test_offset_helper():
    assert offset(paginate(total=30, page=1, per_page=10)) == 0
    assert offset(paginate(total=30, page=2, per_page=10)) == 10
    assert offset(paginate(total=30, page=3, per_page=10)) == 20
