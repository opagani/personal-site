from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.blog_utils import slugify, unique_slug
from backend.db import Base
from backend.models import Post


def _session_with_posts(*titles_slugs):
    e = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(e)
    s = Session(e)
    for title, slug in titles_slugs:
        s.add(Post(slug=slug, title=title, body_md="x"))
    s.commit()
    return s


def test_slugify_basic():
    assert slugify("Hello World") == "hello-world"


def test_slugify_strips_punctuation_and_collapses_runs():
    assert slugify("Hello, World!  This is a test.") == "hello-world-this-is-a-test"


def test_slugify_lowercases_and_handles_unicode():
    out = slugify("Café — naïve")
    assert out == "cafe-naive"


def test_slugify_falls_back_to_default_for_empty_or_punctuation_only():
    assert slugify("") == "post"
    assert slugify("!!!") == "post"


def test_slugify_truncates_to_80_chars():
    out = slugify("a" * 200)
    assert len(out) <= 80


def test_unique_slug_returns_base_when_no_conflict():
    s = _session_with_posts(("Other", "other"))
    assert unique_slug(s, "fresh") == "fresh"


def test_unique_slug_appends_suffix_on_conflict():
    s = _session_with_posts(("First", "hello"), ("Second", "hello-2"))
    assert unique_slug(s, "hello") == "hello-3"


def test_unique_slug_excludes_self_when_editing():
    s = _session_with_posts(("Mine", "mine"))
    p = s.query(Post).filter_by(slug="mine").one()
    assert unique_slug(s, "mine", exclude_id=p.id) == "mine"
