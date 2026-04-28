"""Helpers for blog post slugs."""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Post

MAX_SLUG_LEN = 80


def slugify(title: str) -> str:
    """Lowercase ASCII slug. Returns 'post' for inputs that produce empty slugs."""
    normalized = (
        unicodedata.normalize("NFKD", title or "")
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    s = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
    return (s or "post")[:MAX_SLUG_LEN]


def unique_slug(db: Session, base: str, *, exclude_id: int | None = None) -> str:
    """Return `base` if free; else append -2, -3, … until unique.

    `exclude_id` lets a post keep its own slug while editing.
    """
    base = base or "post"
    candidate = base
    n = 2
    while True:
        stmt = select(Post.id).where(Post.slug == candidate)
        if exclude_id is not None:
            stmt = stmt.where(Post.id != exclude_id)
        if db.scalar(stmt) is None:
            return candidate
        candidate = f"{base}-{n}"
        n += 1
