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
