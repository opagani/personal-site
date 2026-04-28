import re

from sqlalchemy import select

from backend.models import Comment, Post


def _csrf(client, path):
    r = client.get(path)
    assert r.status_code == 200, f"GET {path} returned {r.status_code}"
    m = re.search(r'name="csrf"\s+value="([^"]+)"', r.text)
    assert m, f"CSRF token not found in form HTML at {path}"
    return m.group(1)


# --- post CRUD ---


def test_admin_posts_list_empty(signed_in_client):
    r = signed_in_client.get("/admin/posts")
    assert r.status_code == 200
    assert "+ New post" in r.text


def test_create_post_with_auto_slug(signed_in_client, db_factory):
    csrf = _csrf(signed_in_client, "/admin/posts/new")
    r = signed_in_client.post(
        "/admin/posts/new",
        data={
            "csrf": csrf,
            "title": "Hello World",
            "slug": "",
            "excerpt": "First.",
            "body_md": "# Hi\n\nBody.",
            "published": "on",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    Session = db_factory
    with Session() as s:
        p = s.scalar(select(Post).where(Post.title == "Hello World"))
        assert p is not None
        assert p.slug == "hello-world"
        assert p.published is True
        assert p.published_at is not None


def test_create_post_with_explicit_slug(signed_in_client, db_factory):
    csrf = _csrf(signed_in_client, "/admin/posts/new")
    signed_in_client.post(
        "/admin/posts/new",
        data={
            "csrf": csrf,
            "title": "X",
            "slug": "my-custom-slug",
            "excerpt": "",
            "body_md": "x",
        },
        follow_redirects=False,
    )
    Session = db_factory
    with Session() as s:
        assert s.scalar(select(Post).where(Post.slug == "my-custom-slug")) is not None


def test_create_post_slug_conflict_appends_suffix(signed_in_client, db_factory):
    Session = db_factory
    with Session() as s:
        s.add(Post(slug="hello-world", title="Old", body_md="x"))
        s.commit()
    csrf = _csrf(signed_in_client, "/admin/posts/new")
    signed_in_client.post(
        "/admin/posts/new",
        data={"csrf": csrf, "title": "Hello World", "slug": "", "excerpt": "", "body_md": "y"},
        follow_redirects=False,
    )
    with Session() as s:
        slugs = sorted(p.slug for p in s.scalars(select(Post)).all())
        assert slugs == ["hello-world", "hello-world-2"]


def test_edit_post_keeps_its_own_slug(signed_in_client, db_factory):
    Session = db_factory
    with Session() as s:
        s.add(Post(slug="mine", title="Mine", body_md="x"))
        s.commit()
        pid = s.scalar(select(Post.id).where(Post.slug == "mine"))

    csrf = _csrf(signed_in_client, f"/admin/posts/{pid}")
    r = signed_in_client.post(
        f"/admin/posts/{pid}",
        data={
            "csrf": csrf,
            "title": "Mine renamed",
            "slug": "mine",
            "excerpt": "",
            "body_md": "y",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    with Session() as s:
        p = s.scalar(select(Post).where(Post.id == pid))
        assert p.title == "Mine renamed"
        assert p.slug == "mine"


def test_publish_toggle_sets_published_at_only_first_time(
    signed_in_client, db_factory
):
    Session = db_factory
    with Session() as s:
        s.add(Post(slug="t", title="T", body_md="x"))
        s.commit()
        pid = s.scalar(select(Post.id).where(Post.slug == "t"))

    csrf = _csrf(signed_in_client, "/admin/posts")
    signed_in_client.post(
        f"/admin/posts/{pid}/publish",
        data={"csrf": csrf},
        follow_redirects=False,
    )
    with Session() as s:
        p = s.scalar(select(Post).where(Post.id == pid))
        assert p.published is True
        first_pub = p.published_at
        assert first_pub is not None

    csrf = _csrf(signed_in_client, "/admin/posts")
    signed_in_client.post(
        f"/admin/posts/{pid}/publish",
        data={"csrf": csrf},
        follow_redirects=False,
    )
    with Session() as s:
        p = s.scalar(select(Post).where(Post.id == pid))
        assert p.published is False
        assert p.published_at == first_pub

    csrf = _csrf(signed_in_client, "/admin/posts")
    signed_in_client.post(
        f"/admin/posts/{pid}/publish",
        data={"csrf": csrf},
        follow_redirects=False,
    )
    with Session() as s:
        p = s.scalar(select(Post).where(Post.id == pid))
        assert p.published is True
        assert p.published_at == first_pub


def test_delete_post_cascades_to_comments(signed_in_client, db_factory):
    Session = db_factory
    with Session() as s:
        p = Post(slug="d", title="D", body_md="x")
        s.add(p)
        s.commit()
        s.refresh(p)
        s.add(Comment(post_id=p.id, author_name="a", author_email="a@e.com", body="c"))
        s.commit()
        pid = p.id

    csrf = _csrf(signed_in_client, "/admin/posts")
    signed_in_client.post(
        f"/admin/posts/{pid}/delete",
        data={"csrf": csrf},
        follow_redirects=False,
    )
    with Session() as s:
        assert s.scalar(select(Post).where(Post.id == pid)) is None
        assert s.scalars(select(Comment).where(Comment.post_id == pid)).first() is None


def test_get_unknown_post_returns_404(signed_in_client):
    r = signed_in_client.get("/admin/posts/9999")
    assert r.status_code == 404


# --- comment moderation ---


def _seed_post_with_comment(db_factory, *, approved: bool = False):
    Session = db_factory
    with Session() as s:
        p = Post(slug="m", title="M", body_md="x", published=True)
        s.add(p)
        s.commit()
        s.refresh(p)
        c = Comment(
            post_id=p.id,
            author_name="Bob",
            author_email="bob@example.com",
            body="Awaiting review",
            approved=approved,
        )
        s.add(c)
        s.commit()
        return p.id, c.id


def test_admin_comment_queue_lists_pending(signed_in_client, db_factory):
    _seed_post_with_comment(db_factory, approved=False)
    r = signed_in_client.get("/admin/comments")
    assert r.status_code == 200
    assert "Awaiting review" in r.text
    assert "Bob" in r.text


def test_approve_comment_makes_it_public(
    signed_in_client, client, db_factory
):
    _, cid = _seed_post_with_comment(db_factory, approved=False)
    csrf = _csrf(signed_in_client, "/admin/comments")
    r = signed_in_client.post(
        f"/admin/comments/{cid}/approve",
        data={"csrf": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303

    Session = db_factory
    with Session() as s:
        c = s.scalar(select(Comment).where(Comment.id == cid))
        assert c.approved is True
        assert c.approved_at is not None

    # SPA-era: approved comments now come back via the JSON API.
    r = client.get("/api/blog/posts/m")
    bodies = [c["body"] for c in r.json()["comments"]]
    assert "Awaiting review" in bodies


def test_delete_comment_from_admin(signed_in_client, db_factory):
    _, cid = _seed_post_with_comment(db_factory, approved=False)
    csrf = _csrf(signed_in_client, "/admin/comments")
    r = signed_in_client.post(
        f"/admin/comments/{cid}/delete",
        data={"csrf": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303
    Session = db_factory
    with Session() as s:
        assert s.scalar(select(Comment).where(Comment.id == cid)) is None
