import pytest
from sqlalchemy import select

from backend.models import Comment, Link, Post, Project


def _seed_blog(db_factory):
    Session = db_factory
    from datetime import datetime, timezone

    with Session() as s:
        s.add(Post(
            slug="hello",
            title="Hello",
            excerpt="X.",
            body_md="# Body\n\n**bold**",
            published=True,
            published_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        ))
        s.add(Post(slug="draft", title="Draft", body_md="d", published=False))
        s.commit()
        post_id = s.scalar(select(Post.id).where(Post.slug == "hello"))
        s.add(Comment(post_id=post_id, author_name="A", author_email="a@e.com",
                      body="approved", approved=True))
        s.add(Comment(post_id=post_id, author_name="B", author_email="b@e.com",
                      body="pending", approved=False))
        s.commit()


def test_api_site(client):
    r = client.get("/api/site")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Ada Lovelace"
    assert body["headline"] == "Mathematician"
    assert "bio" in body
    assert "avatar_url" in body


def test_api_projects(client, db_factory):
    Session = db_factory
    with Session() as s:
        s.add(Project(title="P1", description="d1", position=0))
        s.add(Project(title="P0", description="d0", position=-1))
        s.commit()

    r = client.get("/api/projects")
    assert r.status_code == 200
    rows = r.json()
    titles = [r["title"] for r in rows]
    assert titles == ["P0", "P1"]
    assert {"id", "title", "description", "link", "position"} <= rows[0].keys()


def test_api_links(client, db_factory):
    Session = db_factory
    with Session() as s:
        s.add(Link(label="GitHub", url="https://github.com/x", position=0))
        s.commit()
    r = client.get("/api/links")
    assert r.status_code == 200
    assert r.json()[0]["url"] == "https://github.com/x"


def test_api_resume(client, db_factory):
    # Clear pdf_path on the seeded singleton so the assertion is
    # deterministic regardless of whether a real resume.pdf is on disk.
    from backend.models import ResumeMeta

    Session = db_factory
    with Session() as s:
        rm = s.get(ResumeMeta, 1)
        rm.pdf_path = None
        s.commit()

    r = client.get("/api/resume")
    assert r.status_code == 200
    body = r.json()
    assert "summary_html" in body
    assert "Summary text." in body["summary_html"]
    assert "pdf_path" in body
    assert "pdf_available" in body
    assert body["pdf_available"] is False


def test_api_blog_posts_lists_only_published(client, db_factory):
    _seed_blog(db_factory)
    r = client.get("/api/blog/posts")
    assert r.status_code == 200
    rows = r.json()
    slugs = [p["slug"] for p in rows]
    assert "hello" in slugs
    assert "draft" not in slugs
    assert {"slug", "title", "excerpt", "published_at"} <= rows[0].keys()


def test_api_blog_post_returns_body_html_and_only_approved_comments(client, db_factory):
    _seed_blog(db_factory)
    r = client.get("/api/blog/posts/hello")
    assert r.status_code == 200
    body = r.json()
    assert "<strong>bold</strong>" in body["body_html"]
    assert "comment_form_token" in body
    bodies = [c["body"] for c in body["comments"]]
    assert "approved" in bodies
    assert "pending" not in bodies
    assert all("author_email" not in c for c in body["comments"])


def test_api_blog_draft_404_for_anonymous(client, db_factory):
    _seed_blog(db_factory)
    r = client.get("/api/blog/posts/draft")
    assert r.status_code == 404


def test_api_blog_draft_visible_to_signed_in_admin(signed_in_client, db_factory):
    _seed_blog(db_factory)
    r = signed_in_client.get("/api/blog/posts/draft")
    assert r.status_code == 200
    assert r.json()["title"] == "Draft"


def test_api_blog_unknown_slug_404(client):
    r = client.get("/api/blog/posts/no-such-thing")
    assert r.status_code == 404


def test_api_comment_submission_happy_path(client, db_factory, monkeypatch):
    import backend.routes.api as api_routes
    monkeypatch.setattr(api_routes, "MIN_ELAPSED_SECONDS", 0)
    _seed_blog(db_factory)

    r = client.get("/api/blog/posts/hello")
    csrf = r.json()["comment_form_token"]

    r = client.post(
        "/api/blog/posts/hello/comments",
        json={
            "csrf": csrf,
            "url": "",
            "author_name": "Alice",
            "author_email": "alice@example.com",
            "body": "Great post!",
        },
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    Session = db_factory
    with Session() as s:
        rows = s.scalars(select(Comment).where(Comment.body == "Great post!")).all()
        assert len(rows) == 1
        assert rows[0].approved is False


def test_api_comment_honeypot_silent_reject(client, db_factory, monkeypatch):
    import backend.routes.api as api_routes
    monkeypatch.setattr(api_routes, "MIN_ELAPSED_SECONDS", 0)
    _seed_blog(db_factory)

    r = client.get("/api/blog/posts/hello")
    csrf = r.json()["comment_form_token"]
    r = client.post(
        "/api/blog/posts/hello/comments",
        json={
            "csrf": csrf,
            "url": "spam-bots-fill-this",
            "author_name": "Bot",
            "author_email": "bot@example.com",
            "body": "buy stuff",
        },
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    Session = db_factory
    with Session() as s:
        rows = s.scalars(select(Comment).where(Comment.author_name == "Bot")).all()
        assert rows == []


def test_api_comment_fast_submit_silent_reject(client, db_factory):
    _seed_blog(db_factory)
    r = client.get("/api/blog/posts/hello")
    csrf = r.json()["comment_form_token"]
    r = client.post(
        "/api/blog/posts/hello/comments",
        json={
            "csrf": csrf,
            "url": "",
            "author_name": "Speedy",
            "author_email": "s@example.com",
            "body": "fast",
        },
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    Session = db_factory
    with Session() as s:
        assert s.scalars(select(Comment).where(Comment.author_name == "Speedy")).all() == []


def test_api_comment_oversize_body_returns_422(client, db_factory, monkeypatch):
    import backend.routes.api as api_routes
    monkeypatch.setattr(api_routes, "MIN_ELAPSED_SECONDS", 0)
    _seed_blog(db_factory)

    r = client.get("/api/blog/posts/hello")
    csrf = r.json()["comment_form_token"]
    r = client.post(
        "/api/blog/posts/hello/comments",
        json={
            "csrf": csrf,
            "url": "",
            "author_name": "Alice",
            "author_email": "alice@example.com",
            "body": "x" * 5000,
        },
    )
    assert r.status_code == 422
    assert "detail" in r.json()


def test_api_comment_invalid_email_returns_422(client, db_factory, monkeypatch):
    import backend.routes.api as api_routes
    monkeypatch.setattr(api_routes, "MIN_ELAPSED_SECONDS", 0)
    _seed_blog(db_factory)

    r = client.get("/api/blog/posts/hello")
    csrf = r.json()["comment_form_token"]
    r = client.post(
        "/api/blog/posts/hello/comments",
        json={
            "csrf": csrf,
            "url": "",
            "author_name": "Alice",
            "author_email": "not-an-email",
            "body": "hi",
        },
    )
    assert r.status_code == 422


def test_api_comment_csrf_mismatch_returns_403(client, db_factory, monkeypatch):
    import backend.routes.api as api_routes
    monkeypatch.setattr(api_routes, "MIN_ELAPSED_SECONDS", 0)
    _seed_blog(db_factory)

    client.get("/api/blog/posts/hello")
    r = client.post(
        "/api/blog/posts/hello/comments",
        json={
            "csrf": "wrong-token",
            "url": "",
            "author_name": "Alice",
            "author_email": "alice@example.com",
            "body": "hi",
        },
    )
    assert r.status_code == 403
