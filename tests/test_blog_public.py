from datetime import datetime, timezone

from backend.models import Post


def _seed_posts(db_factory):
    Session = db_factory
    with Session() as s:
        s.add(Post(
            slug="published-one",
            title="Published One",
            excerpt="First excerpt.",
            body_md="# Hello\n\nBody **one**.",
            published=True,
            published_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        ))
        s.add(Post(
            slug="draft-secret",
            title="Draft Secret",
            body_md="not ready",
            published=False,
        ))
        s.commit()


def test_blog_list_empty_state(client):
    r = client.get("/blog")
    assert r.status_code == 200
    assert "Blog" in r.text
    assert "No posts yet" in r.text or "no posts" in r.text.lower()


def test_blog_list_shows_only_published_posts(client, db_factory):
    _seed_posts(db_factory)
    r = client.get("/blog")
    assert r.status_code == 200
    assert "Published One" in r.text
    assert "First excerpt." in r.text
    assert "Draft Secret" not in r.text


def test_blog_post_detail_renders_markdown(client, db_factory):
    _seed_posts(db_factory)
    r = client.get("/blog/published-one")
    assert r.status_code == 200
    assert "Published One" in r.text
    assert "<strong>one</strong>" in r.text


def test_blog_unknown_slug_404(client):
    r = client.get("/blog/no-such-thing")
    assert r.status_code == 404


def test_blog_draft_404_for_anonymous(client, db_factory):
    _seed_posts(db_factory)
    r = client.get("/blog/draft-secret")
    assert r.status_code == 404


def test_blog_draft_visible_to_signed_in_admin(signed_in_client, db_factory):
    _seed_posts(db_factory)
    r = signed_in_client.get("/blog/draft-secret")
    assert r.status_code == 200
    assert "Draft Secret" in r.text


def test_blog_link_in_public_nav(client):
    r = client.get("/")
    assert 'href="/blog"' in r.text


# --- comment form + anti-spam ---


import re

import pytest
from sqlalchemy import select

from backend.models import Comment


def _csrf_from_form(html: str) -> str:
    m = re.search(r'name="csrf"\s+value="([^"]+)"', html)
    assert m
    return m.group(1)


@pytest.fixture
def published_post(db_factory):
    _seed_posts(db_factory)
    return "published-one"


def test_post_page_has_comment_form_with_csrf_and_honeypot(client, published_post):
    r = client.get(f"/blog/{published_post}")
    assert r.status_code == 200
    assert 'name="csrf"' in r.text
    assert 'name="url"' in r.text
    assert 'name="author_name"' in r.text
    assert 'name="author_email"' in r.text
    assert 'name="body"' in r.text


def test_comment_submission_happy_path(
    client, published_post, db_factory, monkeypatch
):
    import backend.routes.blog as blog_routes
    monkeypatch.setattr(blog_routes, "MIN_ELAPSED_SECONDS", 0)

    r = client.get(f"/blog/{published_post}")
    csrf = _csrf_from_form(r.text)

    r = client.post(
        f"/blog/{published_post}/comments",
        data={
            "csrf": csrf,
            "url": "",
            "author_name": "Alice",
            "author_email": "alice@example.com",
            "body": "Great post!",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"].endswith(f"/blog/{published_post}#thanks")

    Session = db_factory
    with Session() as s:
        cs = s.scalars(select(Comment).where(Comment.body == "Great post!")).all()
        assert len(cs) == 1
        assert cs[0].approved is False


def test_unapproved_comment_is_not_shown_publicly(
    client, published_post, db_factory, monkeypatch
):
    import backend.routes.blog as blog_routes
    monkeypatch.setattr(blog_routes, "MIN_ELAPSED_SECONDS", 0)

    r = client.get(f"/blog/{published_post}")
    csrf = _csrf_from_form(r.text)
    client.post(
        f"/blog/{published_post}/comments",
        data={
            "csrf": csrf,
            "url": "",
            "author_name": "Alice",
            "author_email": "alice@example.com",
            "body": "Should not appear yet",
        },
        follow_redirects=False,
    )
    r = client.get(f"/blog/{published_post}")
    assert "Should not appear yet" not in r.text


def test_honeypot_filled_silently_rejects(
    client, published_post, db_factory, monkeypatch
):
    import backend.routes.blog as blog_routes
    monkeypatch.setattr(blog_routes, "MIN_ELAPSED_SECONDS", 0)

    r = client.get(f"/blog/{published_post}")
    csrf = _csrf_from_form(r.text)
    r = client.post(
        f"/blog/{published_post}/comments",
        data={
            "csrf": csrf,
            "url": "http://spam.example",
            "author_name": "Bot",
            "author_email": "bot@example.com",
            "body": "buy stuff",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"].endswith(f"/blog/{published_post}#thanks")
    Session = db_factory
    with Session() as s:
        cs = s.scalars(select(Comment).where(Comment.author_name == "Bot")).all()
        assert len(cs) == 0


def test_fast_submit_silently_rejects(client, published_post, db_factory):
    r = client.get(f"/blog/{published_post}")
    csrf = _csrf_from_form(r.text)
    r = client.post(
        f"/blog/{published_post}/comments",
        data={
            "csrf": csrf,
            "url": "",
            "author_name": "Speedy",
            "author_email": "s@example.com",
            "body": "fast",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"].endswith(f"/blog/{published_post}#thanks")
    Session = db_factory
    with Session() as s:
        cs = s.scalars(select(Comment).where(Comment.author_name == "Speedy")).all()
        assert len(cs) == 0


def test_oversize_body_returns_form_with_error(
    client, published_post, monkeypatch
):
    import backend.routes.blog as blog_routes
    monkeypatch.setattr(blog_routes, "MIN_ELAPSED_SECONDS", 0)

    r = client.get(f"/blog/{published_post}")
    csrf = _csrf_from_form(r.text)
    r = client.post(
        f"/blog/{published_post}/comments",
        data={
            "csrf": csrf,
            "url": "",
            "author_name": "Alice",
            "author_email": "alice@example.com",
            "body": "x" * 5000,
        },
        follow_redirects=False,
    )
    assert r.status_code == 200
    assert "too long" in r.text.lower() or "max" in r.text.lower() or "400" in r.text


def test_invalid_email_returns_form_with_error(
    client, published_post, monkeypatch
):
    import backend.routes.blog as blog_routes
    monkeypatch.setattr(blog_routes, "MIN_ELAPSED_SECONDS", 0)

    r = client.get(f"/blog/{published_post}")
    csrf = _csrf_from_form(r.text)
    r = client.post(
        f"/blog/{published_post}/comments",
        data={
            "csrf": csrf,
            "url": "",
            "author_name": "Alice",
            "author_email": "not-an-email",
            "body": "hi",
        },
        follow_redirects=False,
    )
    assert r.status_code == 200
    assert "email" in r.text.lower()


def test_thanks_banner_visible_when_fragment_present(client, published_post):
    r = client.get(f"/blog/{published_post}")
    assert 'id="thanks"' in r.text
