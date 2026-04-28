"""Pure pagination math. No FastAPI / SQLAlchemy coupling — easy to unit test."""

from dataclasses import dataclass
from math import ceil


@dataclass
class PageInfo:
    page: int
    per_page: int
    total: int
    total_pages: int
    has_prev: bool
    has_next: bool
    pages: list  # list[int | None]; None marks an ellipsis gap


def paginate(total: int, page: int, per_page: int = 10) -> PageInfo:
    """Compute paginator state.

    `pages` returns a windowed list with ellipsis markers (None values) when
    the total page count is large. Showing all pages up to 7; for more,
    always include first + last + ±1 around the current page.
    """
    total = max(0, total)
    per_page = max(1, per_page)
    total_pages = max(1, ceil(total / per_page))
    page = max(1, min(page, total_pages))

    if total_pages <= 7:
        pages: list = list(range(1, total_pages + 1))
    else:
        candidates = sorted({1, total_pages, page - 1, page, page + 1})
        candidates = [c for c in candidates if 1 <= c <= total_pages]
        pages = []
        prev = 0
        for p in candidates:
            if prev and p - prev > 1:
                pages.append(None)
            pages.append(p)
            prev = p

    return PageInfo(
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
        has_prev=page > 1,
        has_next=page < total_pages,
        pages=pages,
    )


def offset(page_info: PageInfo) -> int:
    return (page_info.page - 1) * page_info.per_page
