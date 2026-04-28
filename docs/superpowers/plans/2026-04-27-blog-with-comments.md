# Blog with comments — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Markdown-bodied blog with anonymous, admin-moderated comments to the existing portfolio site.

**Architecture:** New `Post` and `Comment` ORM tables. Public routes in `backend/routes/blog.py`. Admin routes appended to `backend/routes/admin.py`. Markdown rendering helper extracted from `routes/public.py` into `backend/markdown.py`. Anti-spam via honeypot field + min-elapsed-time check + silent-reject (303 → `#thanks` indistinguishable from real success). Reuses existing session auth, CSRF, `requires_admin` deps.

**Tech Stack:** FastAPI, Jinja2, SQLAlchemy 2.0 (sync), markdown, argon2-cffi, Starlette `SessionMiddleware`, pytest.

**Spec:** `docs/superpowers/specs/2026-04-27-blog-with-comments-design.md`

---

## File structure (target)

```
backend/
  markdown.py               (NEW — render_markdown helper, moved from routes/public.py)
  blog_utils.py             (NEW — slugify, unique_slug)
  models.py                 (modified — add Post, Comment)
  app.py                    (modified — include blog router)
  routes/
    public.py               (modified — import render_markdown from new module)
    blog.py                 (NEW — public blog routes)
    admin.py                (modified — append posts CRUD + comments queue)
frontend/templates/
  base.html                 (modified — add "Blog" to public nav)
  public/
    blog_list.html          (NEW)
    blog_post.html          (NEW — post body + approved comments + comment form)
  admin/
    dashboard.html          (modified — add links to posts + comments)
    post_list.html          (NEW)
    post_form.html          (NEW)
    comment_queue.html      (NEW)
tests/
  test_markdown.py          (NEW — sanity test for moved helper)
  test_blog_utils.py        (NEW — slugify + unique_slug)
  test_blog_models.py       (NEW — Post + Comment schema)
  test_blog_public.py       (NEW — list, detail, comment submit, anti-spam)
  test_blog_admin.py        (NEW — post CRUD + comment moderation)
```

No new dependencies (`markdown` is already added).

---

## Task 1: Extract `render_markdown` into `backend/markdown.py`

**Files:**
- Create: `backend/markdown.py`
- Modify: `backend/routes/public.py`
- Create: `tests/test_markdown.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_markdown.py
from backend.markdown import render_markdown


def test_returns_empty_string_for_falsy_input():
    assert render_markdown(None) == ""
    assert render_markdown("") == ""


def test_renders_basic_markdown():
    out = render_markdown("**hi**")
    assert "<strong>hi</strong>" in out


def test_uses_extra_extension_for_link_text():
    out = render_markdown("[label](https://example.com)")
    assert '<a href="https://example.com">label</a>' in out


def test_sane_lists_keeps_consecutive_lines_in_one_list():
    out = render_markdown("- a\n- b\n- c")
    assert out.count("<li>") == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_markdown.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.markdown'`.

- [ ] **Step 3: Create `backend/markdown.py`**

```python
# backend/markdown.py
"""Single source of Markdown → HTML rendering for the site.

Used by the resume page and the blog.
"""

import markdown as _md


def render_markdown(text: str | None) -> str:
    if not text:
        return ""
    return _md.markdown(text, extensions=["extra", "sane_lists"])
```

- [ ] **Step 4: Update `backend/routes/public.py` to use the new module**

Replace the existing local `_render_markdown` definition + its single call site:

```python
# backend/routes/public.py — top of file imports
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.markdown import render_markdown
from backend.models import Link, Project, ResumeMeta, SiteMeta
```

Delete the local `_render_markdown` helper. In the `resume` handler, replace:

```python
summary_html = _render_markdown(rmeta.summary if rmeta else None)
```

with:

```python
summary_html = render_markdown(rmeta.summary if rmeta else None)
```

- [ ] **Step 5: Run all tests**

Run: `uv run pytest -v`
Expected: 37 (existing) + 4 (new) = 41 passed. Existing resume rendering still works.

- [ ] **Step 6: Commit**

```bash
git add backend/markdown.py backend/routes/public.py tests/test_markdown.py
git commit -m "refactor: extract render_markdown into backend.markdown for reuse"
```

---

## Task 2: Add `Post` and `Comment` models

**Files:**
- Modify: `backend/models.py`
- Create: `tests/test_blog_models.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_blog_models.py
from datetime import datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.db import Base
from backend.models import Comment, Post


def _engine():
    e = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(e)
    return e


def test_post_table_exists_with_expected_columns():
    Base.metadata.create_all(_engine())
    cols = {c.name for c in Post.__table__.columns}
    assert cols == {
        "id", "slug", "title", "excerpt", "body_md",
        "published", "published_at", "created_at", "updated_at",
    }


def test_comment_table_exists_with_expected_columns():
    cols = {c.name for c in Comment.__table__.columns}
    assert cols == {
        "id", "post_id", "author_name", "author_email",
        "body", "created_at", "approved", "approved_at",
    }


def test_can_insert_and_query_post_and_comment():
    e = _engine()
    with Session(e) as s:
        p = Post(slug="hello", title="Hello", body_md="# Hi", published=True)
        s.add(p)
        s.commit()
        s.refresh(p)
        c = Comment(
            post_id=p.id,
            author_name="Alice",
            author_email="a@example.com",
            body="Nice post",
        )
        s.add(c)
        s.commit()

        loaded = s.scalar(select(Post).where(Post.slug == "hello"))
        assert loaded.title == "Hello"
        assert loaded.published is True
        assert loaded.published_at is None  # only set when admin publishes via route

        cs = s.scalars(select(Comment).where(Comment.post_id == p.id)).all()
        assert len(cs) == 1
        assert cs[0].approved is False  # default


def test_post_slug_is_unique():
    import sqlalchemy.exc

    e = _engine()
    with Session(e) as s:
        s.add(Post(slug="dup", title="A", body_md="x"))
        s.commit()
        s.add(Post(slug="dup", title="B", body_md="y"))
        try:
            s.commit()
            raised = False
        except sqlalchemy.exc.IntegrityError:
            raised = True
    assert raised


def test_post_timestamps_default_to_now():
    e = _engine()
    with Session(e) as s:
        p = Post(slug="t", title="T", body_md="x")
        s.add(p)
        s.commit()
        s.refresh(p)
        assert isinstance(p.created_at, datetime)
        assert isinstance(p.updated_at, datetime)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_blog_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'Post'`.

- [ ] **Step 3: Append models to `backend/models.py`**

Append at the end of the file:

```python
# Append to backend/models.py


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_md: Mapped[str] = mapped_column(Text, nullable=False)
    published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_name: Mapped[str] = mapped_column(String(80), nullable=False)
    author_email: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

Add `Boolean` and `ForeignKey` to the existing `from sqlalchemy import …` line at the top of `backend/models.py`. The full top of file should look like:

```python
# backend/models.py — top
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base
```

- [ ] **Step 4: Run tests, expect pass**

Run: `uv run pytest tests/test_blog_models.py tests/test_models.py -v`
Expected: 4 (existing test_models) + 5 (new) = 9 passed. Existing model tests still pass because `users`, `site_meta`, `projects`, `links`, `resume_meta` are untouched.

- [ ] **Step 5: Commit**

```bash
git add backend/models.py tests/test_blog_models.py
git commit -m "feat(blog): add Post and Comment models"
```

---

## Task 3: Slug utility (`slugify` + `unique_slug`)

**Files:**
- Create: `backend/blog_utils.py`
- Create: `tests/test_blog_utils.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_blog_utils.py
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
    # Unicode chars get stripped to their ASCII approximations or removed entirely.
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
    # Editing the same post should NOT bump the slug just because it already exists.
    assert unique_slug(s, "mine", exclude_id=p.id) == "mine"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_blog_utils.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.blog_utils'`.

- [ ] **Step 3: Create `backend/blog_utils.py`**

```python
# backend/blog_utils.py
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
    normalized = unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode("ascii")
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
```

- [ ] **Step 4: Run tests, expect pass**

Run: `uv run pytest tests/test_blog_utils.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/blog_utils.py tests/test_blog_utils.py
git commit -m "feat(blog): slugify + unique_slug helpers"
```

---

## Task 4: Public blog list + post detail (read-only, no comments yet)

**Files:**
- Create: `backend/routes/blog.py`
- Modify: `backend/app.py`
- Modify: `frontend/templates/base.html`
- Create: `frontend/templates/public/blog_list.html`
- Create: `frontend/templates/public/blog_post.html`
- Create: `tests/test_blog_public.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_blog_public.py
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
    # Empty state copy
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
    assert "<strong>one</strong>" in r.text  # markdown rendered


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
```

- [ ] **Step 2: Run tests, expect fail**

Run: `uv run pytest tests/test_blog_public.py -v`
Expected: FAIL — 404 / no Blog in nav / etc.

- [ ] **Step 3: Add Blog to the public nav in `frontend/templates/base.html`**

Edit the `nav` block to include Blog between Projects and Contact:

```html
{% set nav = [('home', '/', 'Home'),
              ('projects', '/projects', 'Projects'),
              ('blog', '/blog', 'Blog'),
              ('contact', '/contact', 'Contact'),
              ('resume', '/resume', 'Resume')] %}
```

- [ ] **Step 4: Create `frontend/templates/public/blog_list.html`**

```html
<!-- frontend/templates/public/blog_list.html -->
{% extends "base.html" %}
{% block title %}Blog · {{ site.name }}{% endblock %}

{% block content %}
<h1>Blog</h1>

{% if posts %}
  <ul class="blog-list">
    {% for p in posts %}
      <li class="blog-list__item">
        <h2><a href="/blog/{{ p.slug }}">{{ p.title }}</a></h2>
        {% if p.published_at %}
          <p class="blog-list__date muted">
            <time datetime="{{ p.published_at.isoformat() }}">
              {{ p.published_at.strftime('%b %-d, %Y') }}
            </time>
          </p>
        {% endif %}
        {% if p.excerpt %}
          <p>{{ p.excerpt }}</p>
        {% endif %}
      </li>
    {% endfor %}
  </ul>
{% else %}
  <p class="muted">No posts yet.</p>
{% endif %}
{% endblock %}
```

- [ ] **Step 5: Create `frontend/templates/public/blog_post.html` (post body only — comments added in Task 5)**

```html
<!-- frontend/templates/public/blog_post.html -->
{% extends "base.html" %}
{% block title %}{{ post.title }} · {{ site.name }}{% endblock %}

{% block content %}
<article class="blog-post">
  {% if not post.published %}
    <p class="muted">Draft — not visible to the public.</p>
  {% endif %}
  <h1>{{ post.title }}</h1>
  {% if post.published_at %}
    <p class="blog-post__date muted">
      <time datetime="{{ post.published_at.isoformat() }}">
        {{ post.published_at.strftime('%b %-d, %Y') }}
      </time>
    </p>
  {% endif %}

  <div class="blog-post__body">
    {{ body_html | safe }}
  </div>
</article>
{% endblock %}
```

- [ ] **Step 6: Create `backend/routes/blog.py`**

```python
# backend/routes/blog.py
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.auth import current_user
from backend.db import get_db
from backend.markdown import render_markdown
from backend.models import Post, SiteMeta

ROOT = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=ROOT / "frontend" / "templates")

router = APIRouter()


def _site_meta(db: Session) -> SiteMeta | None:
    return db.scalar(select(SiteMeta).where(SiteMeta.id == 1))


@router.get("/blog")
def blog_list(request: Request, db: Session = Depends(get_db)):
    posts = db.scalars(
        select(Post)
        .where(Post.published.is_(True))
        .order_by(Post.published_at.desc(), Post.id.desc())
    ).all()
    return templates.TemplateResponse(
        request,
        "public/blog_list.html",
        {"site": _site_meta(db), "posts": posts, "current_page": "blog"},
    )


@router.get("/blog/{slug}")
def blog_post(slug: str, request: Request, db: Session = Depends(get_db)):
    post = db.scalar(select(Post).where(Post.slug == slug))
    if post is None:
        raise HTTPException(status_code=404)
    if not post.published and current_user(request, db) is None:
        # Drafts are hidden from anonymous viewers but visible to signed-in admin.
        raise HTTPException(status_code=404)
    body_html = render_markdown(post.body_md)
    return templates.TemplateResponse(
        request,
        "public/blog_post.html",
        {
            "site": _site_meta(db),
            "post": post,
            "body_html": body_html,
            "current_page": "blog",
        },
    )
```

- [ ] **Step 7: Mount the blog router in `backend/app.py`**

Add the import and `include_router` call:

```python
# backend/app.py — modify imports
from backend.routes.admin import router as admin_router
from backend.routes.blog import router as blog_router  # NEW
from backend.routes.public import router as public_router
```

```python
# backend/app.py — modify the bottom of the module
app.include_router(public_router)
app.include_router(blog_router)   # NEW
app.include_router(admin_router)
```

- [ ] **Step 8: Run tests, expect pass**

Run: `uv run pytest tests/test_blog_public.py -v`
Expected: 7 passed.

- [ ] **Step 9: Run full suite to confirm nothing else broke**

Run: `uv run pytest -v`
Expected: all green.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "feat(blog): public list + post detail (markdown body, draft preview for admin)"
```

---

## Task 5: Comment form + submission + anti-spam

**Files:**
- Modify: `backend/routes/blog.py` (add comment form rendering + POST handler + constants)
- Modify: `frontend/templates/public/blog_post.html` (add comments section + form + thanks banner)
- Modify: `frontend/static/styles.css` (honeypot CSS)
- Modify: `tests/test_blog_public.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_blog_public.py`:

```python
import re

import pytest
from sqlalchemy import select

from backend.models import Comment


# --- helpers ---


def _csrf_from_form(html: str) -> str:
    m = re.search(r'name="csrf"\s+value="([^"]+)"', html)
    assert m
    return m.group(1)


@pytest.fixture
def published_post(db_factory):
    _seed_posts(db_factory)
    return "published-one"


# --- tests ---


def test_post_page_has_comment_form_with_csrf_and_honeypot(client, published_post):
    r = client.get(f"/blog/{published_post}")
    assert r.status_code == 200
    assert 'name="csrf"' in r.text
    # Honeypot is the literal `name="url"` field
    assert 'name="url"' in r.text
    assert 'name="author_name"' in r.text
    assert 'name="author_email"' in r.text
    assert 'name="body"' in r.text


def test_comment_submission_happy_path(
    client, published_post, db_factory, monkeypatch
):
    # Drop the elapsed-time threshold so this test doesn't have to sleep.
    import backend.routes.blog as blog_routes
    monkeypatch.setattr(blog_routes, "MIN_ELAPSED_SECONDS", 0)

    r = client.get(f"/blog/{published_post}")
    csrf = _csrf_from_form(r.text)

    r = client.post(
        f"/blog/{published_post}/comments",
        data={
            "csrf": csrf,
            "url": "",  # honeypot empty
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
        assert cs[0].approved is False  # awaiting moderation


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
            "url": "http://spam.example",  # bot-filled honeypot
            "author_name": "Bot",
            "author_email": "bot@example.com",
            "body": "buy stuff",
        },
        follow_redirects=False,
    )
    # Same 303 → #thanks as a successful submission. Indistinguishable.
    assert r.status_code == 303
    assert r.headers["location"].endswith(f"/blog/{published_post}#thanks")
    Session = db_factory
    with Session() as s:
        cs = s.scalars(select(Comment).where(Comment.author_name == "Bot")).all()
        assert len(cs) == 0


def test_fast_submit_silently_rejects(client, published_post, db_factory):
    # Default MIN_ELAPSED_SECONDS = 3; the test client posts immediately,
    # which is < 3 seconds → silent reject.
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
            "body": "x" * 5000,  # > MAX_BODY_LEN = 4000
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
    # The page itself doesn't know about #thanks (browsers don't send fragments
    # to the server). The template renders an always-present banner element
    # that's hidden via :target CSS — verify the element exists.
    r = client.get(f"/blog/{published_post}")
    assert 'id="thanks"' in r.text
```

- [ ] **Step 2: Run new tests, expect failures**

Run: `uv run pytest tests/test_blog_public.py -v`
Expected: prior 7 still pass; new 8 fail because the form doesn't exist / POST 404s.

- [ ] **Step 3: Add anti-spam constants + form-state setup to `backend/routes/blog.py`**

Replace the file with the version below (extends Task 4's content):

```python
# backend/routes/blog.py
import re
import time
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.auth import (
    csrf_form_field,
    current_user,
    ensure_csrf_token,
    verify_csrf,
)
from backend.db import get_db
from backend.markdown import render_markdown
from backend.models import Comment, Post, SiteMeta

ROOT = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=ROOT / "frontend" / "templates")

router = APIRouter()

# Anti-spam tunables (test-overridable)
MIN_ELAPSED_SECONDS = 3
MAX_NAME_LEN = 80
MAX_EMAIL_LEN = 120
MAX_BODY_LEN = 4000
MIN_BODY_LEN = 1
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
SESSION_KEY_FORM_TS = "comment_form_ts"


def _site_meta(db: Session) -> SiteMeta | None:
    return db.scalar(select(SiteMeta).where(SiteMeta.id == 1))


def _record_form_render(request: Request, slug: str) -> None:
    request.session[SESSION_KEY_FORM_TS] = {"slug": slug, "ts": int(time.time())}


def _elapsed_too_short(request: Request, slug: str) -> bool:
    info = request.session.get(SESSION_KEY_FORM_TS)
    if not info or info.get("slug") != slug:
        return True
    return (int(time.time()) - int(info.get("ts", 0))) < MIN_ELAPSED_SECONDS


def _silent_reject(slug: str) -> RedirectResponse:
    """Indistinguishable from a real success: 303 → #thanks, no DB write."""
    return RedirectResponse(url=f"/blog/{slug}#thanks", status_code=303)


def _render_post(
    request: Request,
    db: Session,
    post: Post,
    *,
    form: dict | None = None,
    errors: list[str] | None = None,
) -> "templates.TemplateResponse":
    approved_comments = db.scalars(
        select(Comment)
        .where(Comment.post_id == post.id, Comment.approved.is_(True))
        .order_by(Comment.created_at.asc(), Comment.id.asc())
    ).all()
    return templates.TemplateResponse(
        request,
        "public/blog_post.html",
        {
            "site": _site_meta(db),
            "post": post,
            "body_html": render_markdown(post.body_md),
            "comments": approved_comments,
            "csrf_token": ensure_csrf_token(request),
            "form": form or {"author_name": "", "author_email": "", "body": ""},
            "errors": errors or [],
            "current_page": "blog",
        },
        status_code=200,
    )


@router.get("/blog")
def blog_list(request: Request, db: Session = Depends(get_db)):
    posts = db.scalars(
        select(Post)
        .where(Post.published.is_(True))
        .order_by(Post.published_at.desc(), Post.id.desc())
    ).all()
    return templates.TemplateResponse(
        request,
        "public/blog_list.html",
        {"site": _site_meta(db), "posts": posts, "current_page": "blog"},
    )


@router.get("/blog/{slug}")
def blog_post(slug: str, request: Request, db: Session = Depends(get_db)):
    post = db.scalar(select(Post).where(Post.slug == slug))
    if post is None:
        raise HTTPException(status_code=404)
    if not post.published and current_user(request, db) is None:
        raise HTTPException(status_code=404)
    _record_form_render(request, slug)
    return _render_post(request, db, post)


@router.post("/blog/{slug}/comments")
def submit_comment(
    slug: str,
    request: Request,
    db: Session = Depends(get_db),
    csrf: str = Depends(csrf_form_field),
    url: str = Form(""),
    author_name: str = Form(""),
    author_email: str = Form(""),
    body: str = Form(""),
):
    # CSRF check first — bots without a session never get here.
    verify_csrf(request, csrf)

    post = db.scalar(select(Post).where(Post.slug == slug))
    if post is None:
        raise HTTPException(status_code=404)
    if not post.published and current_user(request, db) is None:
        raise HTTPException(status_code=404)

    # Silent-reject: honeypot field set, OR submitted faster than humans can type.
    if url.strip():
        return _silent_reject(slug)
    if _elapsed_too_short(request, slug):
        return _silent_reject(slug)

    # Real validation — show errors to the user.
    name = author_name.strip()
    email = author_email.strip()
    body_clean = body.strip()
    errors: list[str] = []
    if not (1 <= len(name) <= MAX_NAME_LEN):
        errors.append(f"Name must be 1–{MAX_NAME_LEN} characters.")
    if not (5 <= len(email) <= MAX_EMAIL_LEN) or not EMAIL_RE.fullmatch(email):
        errors.append("Enter a valid email address.")
    if not (MIN_BODY_LEN <= len(body_clean) <= MAX_BODY_LEN):
        errors.append(f"Comment must be {MIN_BODY_LEN}–{MAX_BODY_LEN} characters.")

    if errors:
        return _render_post(
            request, db, post,
            form={"author_name": name, "author_email": email, "body": body_clean},
            errors=errors,
        )

    db.add(Comment(
        post_id=post.id,
        author_name=name,
        author_email=email,
        body=body_clean,
    ))
    db.commit()
    return RedirectResponse(url=f"/blog/{slug}#thanks", status_code=303)
```

- [ ] **Step 4: Update `frontend/templates/public/blog_post.html` with comments + form**

Replace the entire file:

```html
<!-- frontend/templates/public/blog_post.html -->
{% extends "base.html" %}
{% block title %}{{ post.title }} · {{ site.name }}{% endblock %}

{% block content %}
<article class="blog-post">
  {% if not post.published %}
    <p class="muted">Draft — not visible to the public.</p>
  {% endif %}

  <h1>{{ post.title }}</h1>
  {% if post.published_at %}
    <p class="blog-post__date muted">
      <time datetime="{{ post.published_at.isoformat() }}">
        {{ post.published_at.strftime('%b %-d, %Y') }}
      </time>
    </p>
  {% endif %}

  <div class="blog-post__body">
    {{ body_html | safe }}
  </div>
</article>

<section class="comments" aria-label="Comments">
  <h2>Comments</h2>

  {# :target CSS shows this only when the URL fragment is #thanks. #}
  <div id="thanks" class="thanks-banner">
    Thanks — your comment is awaiting moderation.
  </div>

  {% if comments %}
    <ul class="comment-list">
      {% for c in comments %}
        <li class="comment">
          <p class="comment__meta">
            <strong>{{ c.author_name }}</strong>
            <time class="muted" datetime="{{ c.created_at.isoformat() }}">
              · {{ c.created_at.strftime('%b %-d, %Y') }}
            </time>
          </p>
          <p class="comment__body">{{ c.body }}</p>
        </li>
      {% endfor %}
    </ul>
  {% else %}
    <p class="muted">No comments yet — be the first.</p>
  {% endif %}

  {% if errors %}
    <ul class="error">
      {% for e in errors %}<li>{{ e }}</li>{% endfor %}
    </ul>
  {% endif %}

  <form method="post" action="/blog/{{ post.slug }}/comments" class="admin-form comment-form">
    <input type="hidden" name="csrf" value="{{ csrf_token }}">
    {# Honeypot: bots fill every input; humans never see this one. #}
    <div class="hp" aria-hidden="true">
      <label>Leave this field blank
        <input type="text" name="url" value="" tabindex="-1" autocomplete="off">
      </label>
    </div>
    <label>Name
      <input name="author_name" value="{{ form.author_name }}" required maxlength="80">
    </label>
    <label>Email <span class="muted">(not published)</span>
      <input name="author_email" type="email" value="{{ form.author_email }}" required maxlength="120">
    </label>
    <label>Comment
      <textarea name="body" rows="5" required maxlength="4000">{{ form.body }}</textarea>
    </label>
    <button type="submit">Post comment</button>
  </form>
</section>
{% endblock %}
```

- [ ] **Step 5: Add comment + honeypot CSS to `frontend/static/styles.css`**

Append at the end of the file:

```css
/* --- Blog --- */

.blog-list { list-style: none; padding: 0; display: grid; gap: 1.25rem; }
.blog-list__item h2 { margin: 0 0 0.25rem; }
.blog-list__date { margin: 0 0 0.5rem; font-size: 0.9rem; }

.blog-post__date { margin: 0 0 1.25rem; font-size: 0.95rem; }
.blog-post__body h2 { margin-top: 1.5rem; }
.blog-post__body img { max-width: 100%; }

.comments { margin-top: 2.5rem; border-top: 1px solid var(--border); padding-top: 1.5rem; }
.comments h2 { font-size: 1.1rem; margin: 0 0 1rem; }

.comment-list { list-style: none; padding: 0; display: grid; gap: 1rem; margin: 0 0 1.5rem; }
.comment { border: 1px solid var(--border); border-radius: 8px; padding: 0.75rem 1rem; }
.comment__meta { margin: 0 0 0.35rem; }
.comment__body { margin: 0; white-space: pre-wrap; }

.comment-form { margin-top: 1rem; }

/* :target makes the banner visible only when the URL fragment is #thanks. */
.thanks-banner { display: none; }
#thanks:target { display: block; padding: 0.6rem 0.85rem; border-radius: 6px;
                 background: #ecfeff; color: #0e7490; margin-bottom: 1rem; }
@media (prefers-color-scheme: dark) {
  #thanks:target { background: #0c4a6e; color: #cffafe; }
}

/* Honeypot — visually hidden but still focusable to keep WCAG happy. */
.hp { position: absolute; left: -10000px; width: 1px; height: 1px; overflow: hidden; }
```

- [ ] **Step 6: Run new tests, expect pass**

Run: `uv run pytest tests/test_blog_public.py -v`
Expected: 15 passed (7 from Task 4 + 8 new).

- [ ] **Step 7: Run full suite**

Run: `uv run pytest -v`
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat(blog): comment form + anti-spam (honeypot + min-elapsed silent-reject)"
```

---

## Task 6: Admin posts CRUD

**Files:**
- Modify: `backend/routes/admin.py` (append posts routes)
- Create: `frontend/templates/admin/post_list.html`
- Create: `frontend/templates/admin/post_form.html`
- Modify: `frontend/templates/admin/dashboard.html` (add Posts link)
- Create: `tests/test_blog_admin.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_blog_admin.py
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
            "slug": "mine",  # unchanged
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

    # Publish #1 — sets published_at
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

    # Unpublish — keeps published_at
    csrf = _csrf(signed_in_client, "/admin/posts")
    signed_in_client.post(
        f"/admin/posts/{pid}/publish",
        data={"csrf": csrf},
        follow_redirects=False,
    )
    with Session() as s:
        p = s.scalar(select(Post).where(Post.id == pid))
        assert p.published is False
        assert p.published_at == first_pub  # unchanged

    # Re-publish — also keeps the original published_at
    csrf = _csrf(signed_in_client, "/admin/posts")
    signed_in_client.post(
        f"/admin/posts/{pid}/publish",
        data={"csrf": csrf},
        follow_redirects=False,
    )
    with Session() as s:
        p = s.scalar(select(Post).where(Post.id == pid))
        assert p.published is True
        assert p.published_at == first_pub  # still the original


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
```

- [ ] **Step 2: Run new tests, expect 404 / route-missing failures**

Run: `uv run pytest tests/test_blog_admin.py -v`
Expected: FAIL (routes don't exist yet).

- [ ] **Step 3: Append post routes to `backend/routes/admin.py`**

Add these imports near the top of `backend/routes/admin.py` (alongside the existing model imports):

```python
from datetime import datetime, timezone

from backend.blog_utils import slugify, unique_slug
from backend.models import Comment, Post  # extend the existing import line
```

(If the existing import line already exists, merge the new model names into it.)

Append the routes after the existing project/link routes:

```python
# --- posts CRUD ---


@router.get("/posts")
def posts_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(requires_admin),
):
    rows = db.scalars(
        select(Post).order_by(Post.published.asc(), Post.updated_at.desc())
    ).all()
    return templates.TemplateResponse(
        request,
        "admin/post_list.html",
        {
            "site": _site_meta(db),
            "posts": rows,
            "user": user,
            "csrf_token": ensure_csrf_token(request),
            "current_page": None,
        },
    )


def _post_form_context(request, db, *, post, is_new, user):
    return {
        "site": _site_meta(db),
        "post": post,
        "is_new": is_new,
        "user": user,
        "csrf_token": ensure_csrf_token(request),
        "current_page": None,
    }


@router.get("/posts/new")
def post_new_form(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(requires_admin),
):
    blank = SimpleNamespace(
        id=None, title="", slug="", excerpt="", body_md="", published=False
    )
    return templates.TemplateResponse(
        request, "admin/post_form.html",
        _post_form_context(request, db, post=blank, is_new=True, user=user),
    )


@router.post("/posts/new")
def post_create(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(requires_admin_post),
    title: str = Form(...),
    slug: str = Form(""),
    excerpt: str = Form(""),
    body_md: str = Form(...),
    published: str = Form(""),  # checkbox returns "on" or empty
):
    base = slugify(slug.strip()) if slug.strip() else slugify(title)
    final_slug = unique_slug(db, base)
    is_published = bool(published)
    p = Post(
        slug=final_slug,
        title=title.strip(),
        excerpt=(excerpt.strip() or None),
        body_md=body_md,
        published=is_published,
        published_at=datetime.now(timezone.utc) if is_published else None,
    )
    db.add(p)
    db.commit()
    return RedirectResponse(url="/admin/posts", status_code=303)


@router.get("/posts/{post_id}")
def post_edit_form(
    post_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(requires_admin),
):
    p = db.scalar(select(Post).where(Post.id == post_id))
    if p is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return templates.TemplateResponse(
        request, "admin/post_form.html",
        _post_form_context(request, db, post=p, is_new=False, user=user),
    )


@router.post("/posts/{post_id}")
def post_update(
    post_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(requires_admin_post),
    title: str = Form(...),
    slug: str = Form(""),
    excerpt: str = Form(""),
    body_md: str = Form(...),
    published: str = Form(""),
):
    p = db.scalar(select(Post).where(Post.id == post_id))
    if p is None:
        raise HTTPException(status_code=404, detail="Post not found")

    base = slugify(slug.strip()) if slug.strip() else slugify(title)
    p.slug = unique_slug(db, base, exclude_id=p.id)
    p.title = title.strip()
    p.excerpt = excerpt.strip() or None
    p.body_md = body_md

    new_pub = bool(published)
    if new_pub and not p.published and p.published_at is None:
        p.published_at = datetime.now(timezone.utc)
    p.published = new_pub
    db.commit()
    return RedirectResponse(url="/admin/posts", status_code=303)


@router.post("/posts/{post_id}/publish")
def post_publish_toggle(
    post_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(requires_admin_post),
):
    p = db.scalar(select(Post).where(Post.id == post_id))
    if p is None:
        raise HTTPException(status_code=404, detail="Post not found")
    new_state = not p.published
    if new_state and p.published_at is None:
        p.published_at = datetime.now(timezone.utc)
    p.published = new_state
    db.commit()
    return RedirectResponse(url="/admin/posts", status_code=303)


@router.post("/posts/{post_id}/delete")
def post_delete(
    post_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(requires_admin_post),
):
    p = db.scalar(select(Post).where(Post.id == post_id))
    if p is None:
        raise HTTPException(status_code=404, detail="Post not found")
    db.delete(p)
    db.commit()
    return RedirectResponse(url="/admin/posts", status_code=303)
```

- [ ] **Step 4: Create `frontend/templates/admin/post_list.html`**

```html
<!-- frontend/templates/admin/post_list.html -->
{% extends "admin/base.html" %}
{% block title %}Posts · {{ site.name }}{% endblock %}

{% block admin %}
<p><a href="/admin">← back to dashboard</a></p>
<h1>Posts</h1>
<p><a class="button" href="/admin/posts/new">+ New post</a></p>

{% if posts %}
  <ul class="admin-list">
    {% for p in posts %}
      <li>
        <strong><a href="/admin/posts/{{ p.id }}">{{ p.title }}</a></strong>
        <span class="muted">
          · {{ "Published" if p.published else "Draft" }}
          · /blog/{{ p.slug }}
        </span>
        <form method="post" action="/admin/posts/{{ p.id }}/publish" style="display:inline">
          <input type="hidden" name="csrf" value="{{ csrf_token }}">
          <button class="link-button" type="submit">{{ "unpublish" if p.published else "publish" }}</button>
        </form>
        <form method="post" action="/admin/posts/{{ p.id }}/delete" style="display:inline">
          <input type="hidden" name="csrf" value="{{ csrf_token }}">
          <button class="link-button" type="submit"
                  onclick="return confirm('Delete &quot;{{ p.title }}&quot; and all its comments?');">delete</button>
        </form>
      </li>
    {% endfor %}
  </ul>
{% else %}
  <p class="muted">No posts yet.</p>
{% endif %}
{% endblock %}
```

- [ ] **Step 5: Create `frontend/templates/admin/post_form.html`**

```html
<!-- frontend/templates/admin/post_form.html -->
{% extends "admin/base.html" %}
{% block title %}{{ "New" if is_new else "Edit" }} post · {{ site.name }}{% endblock %}

{% block admin %}
<p><a href="/admin/posts">← back to posts</a></p>
<h1>{{ "New post" if is_new else "Edit post" }}</h1>

<form method="post" action="{{ '/admin/posts/new' if is_new else '/admin/posts/' ~ post.id }}" class="admin-form">
  <input type="hidden" name="csrf" value="{{ csrf_token }}">
  <label>Title
    <input name="title" value="{{ post.title or '' }}" required maxlength="200">
  </label>
  <label>Slug
    <input name="slug" value="{{ post.slug or '' }}" maxlength="120">
    <small class="muted">Leave blank to auto-generate from the title.</small>
  </label>
  <label>Excerpt (optional)
    <textarea name="excerpt" rows="2">{{ post.excerpt or '' }}</textarea>
    <small class="muted">Short blurb shown on the blog list page.</small>
  </label>
  <label>Body
    <textarea name="body_md" rows="22" required>{{ post.body_md or '' }}</textarea>
    <small class="muted">
      Markdown supported. <code>## heading</code>, <code>**bold**</code>,
      <code>- bullet</code>. Blank lines separate blocks.
    </small>
  </label>
  <label class="admin-checkbox">
    <input type="checkbox" name="published" {% if post.published %}checked{% endif %}>
    Published
  </label>
  <button type="submit">{{ "Create" if is_new else "Save" }}</button>
</form>
{% endblock %}
```

- [ ] **Step 6: Add Posts link to `frontend/templates/admin/dashboard.html`**

Replace the dashboard's `<ul>` with:

```html
<ul class="admin-nav">
  <li><a href="/admin/site">Edit site (name, headline, bio)</a></li>
  <li><a href="/admin/posts">Manage blog posts</a></li>
  <li><a href="/admin/comments">Moderate comments</a></li>
  <li><a href="/admin/projects">Manage projects</a></li>
  <li><a href="/admin/links">Manage contact links</a></li>
  <li><a href="/admin/resume">Edit resume</a></li>
</ul>
```

- [ ] **Step 7: Append checkbox CSS to `frontend/static/styles.css`**

```css
.admin-checkbox { display: flex; flex-direction: row !important; align-items: center; gap: 0.5rem; }
.admin-checkbox input { width: auto; }
```

- [ ] **Step 8: Run new tests, expect pass**

Run: `uv run pytest tests/test_blog_admin.py -v`
Expected: 8 passed.

- [ ] **Step 9: Run full suite**

Run: `uv run pytest -v`
Expected: all green.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "feat(admin): blog post CRUD with slug auto-gen + publish toggle"
```

---

## Task 7: Admin comment moderation

**Files:**
- Modify: `backend/routes/admin.py` (append comment routes)
- Create: `frontend/templates/admin/comment_queue.html`
- Modify: `tests/test_blog_admin.py` (append moderation tests)

- [ ] **Step 1: Append failing tests**

Append to `tests/test_blog_admin.py`:

```python
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

    # Public post page now shows the comment.
    r = client.get("/blog/m")
    assert "Awaiting review" in r.text


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
```

- [ ] **Step 2: Run new tests, expect fail**

Run: `uv run pytest tests/test_blog_admin.py -v`
Expected: 8 prior pass; 3 new fail with 404.

- [ ] **Step 3: Append comment routes to `backend/routes/admin.py`**

```python
# --- comment moderation ---


@router.get("/comments")
def comments_queue(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(requires_admin),
):
    pending = db.scalars(
        select(Comment)
        .where(Comment.approved.is_(False))
        .order_by(Comment.created_at.desc())
    ).all()
    approved = db.scalars(
        select(Comment)
        .where(Comment.approved.is_(True))
        .order_by(Comment.approved_at.desc())
        .limit(20)
    ).all()
    # Build a {comment_id: post} map for the template (avoid N+1 in Jinja).
    post_ids = {c.post_id for c in (*pending, *approved)}
    posts = {
        p.id: p
        for p in db.scalars(select(Post).where(Post.id.in_(post_ids))).all()
    } if post_ids else {}
    return templates.TemplateResponse(
        request,
        "admin/comment_queue.html",
        {
            "site": _site_meta(db),
            "pending": pending,
            "approved": approved,
            "posts": posts,
            "user": user,
            "csrf_token": ensure_csrf_token(request),
            "current_page": None,
        },
    )


@router.post("/comments/{comment_id}/approve")
def comment_approve(
    comment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(requires_admin_post),
):
    c = db.scalar(select(Comment).where(Comment.id == comment_id))
    if c is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    if not c.approved:
        c.approved = True
        c.approved_at = datetime.now(timezone.utc)
    db.commit()
    return RedirectResponse(url="/admin/comments", status_code=303)


@router.post("/comments/{comment_id}/delete")
def comment_delete(
    comment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(requires_admin_post),
):
    c = db.scalar(select(Comment).where(Comment.id == comment_id))
    if c is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    db.delete(c)
    db.commit()
    return RedirectResponse(url="/admin/comments", status_code=303)
```

- [ ] **Step 4: Create `frontend/templates/admin/comment_queue.html`**

```html
<!-- frontend/templates/admin/comment_queue.html -->
{% extends "admin/base.html" %}
{% block title %}Comments · {{ site.name }}{% endblock %}

{% block admin %}
<p><a href="/admin">← back to dashboard</a></p>
<h1>Comments</h1>

<h2>Pending {% if pending %}<span class="muted">({{ pending|length }})</span>{% endif %}</h2>
{% if pending %}
  <ul class="admin-list">
    {% for c in pending %}
      {% set p = posts[c.post_id] %}
      <li>
        <p>
          <strong>{{ c.author_name }}</strong>
          <span class="muted">&lt;{{ c.author_email }}&gt;</span>
          {% if p %}
            on <a href="/blog/{{ p.slug }}">{{ p.title }}</a>
          {% endif %}
          <span class="muted">· {{ c.created_at.strftime('%b %-d, %Y %H:%M') }}</span>
        </p>
        <p style="white-space: pre-wrap">{{ c.body }}</p>
        <form method="post" action="/admin/comments/{{ c.id }}/approve" style="display:inline">
          <input type="hidden" name="csrf" value="{{ csrf_token }}">
          <button class="link-button" type="submit">approve</button>
        </form>
        <form method="post" action="/admin/comments/{{ c.id }}/delete" style="display:inline">
          <input type="hidden" name="csrf" value="{{ csrf_token }}">
          <button class="link-button" type="submit"
                  onclick="return confirm('Delete this comment?');">delete</button>
        </form>
      </li>
    {% endfor %}
  </ul>
{% else %}
  <p class="muted">Nothing pending.</p>
{% endif %}

<h2>Recently approved</h2>
{% if approved %}
  <ul class="admin-list">
    {% for c in approved %}
      {% set p = posts[c.post_id] %}
      <li>
        <p>
          <strong>{{ c.author_name }}</strong>
          {% if p %}on <a href="/blog/{{ p.slug }}">{{ p.title }}</a>{% endif %}
          <span class="muted">· {{ c.approved_at.strftime('%b %-d, %Y') }}</span>
        </p>
        <p style="white-space: pre-wrap">{{ c.body }}</p>
        <form method="post" action="/admin/comments/{{ c.id }}/delete" style="display:inline">
          <input type="hidden" name="csrf" value="{{ csrf_token }}">
          <button class="link-button" type="submit"
                  onclick="return confirm('Delete this comment?');">delete</button>
        </form>
      </li>
    {% endfor %}
  </ul>
{% else %}
  <p class="muted">No approved comments yet.</p>
{% endif %}
{% endblock %}
```

- [ ] **Step 5: Run new tests, expect pass**

Run: `uv run pytest tests/test_blog_admin.py -v`
Expected: 11 passed.

- [ ] **Step 6: Run full suite**

Run: `uv run pytest -v`
Expected: all green (37 prior + 4 markdown + 5 blog_models + 8 blog_utils + 15 blog_public + 11 blog_admin = 80).

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(admin): comment moderation queue + approve/delete actions"
```

---

## Task 8: README touch-up + final manual e2e smoke

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Append a Blog section to `README.md`**

Add this section after the existing "Editing content" section:

```markdown
## Blog & comments

- Sign into `/admin`, click **Manage blog posts** to write Markdown posts. Save as draft, then click **publish** when ready. Drafts are visible only to signed-in admin (handy for previewing).
- Visitors leave comments on each post page. The form has an invisible honeypot field plus a min-elapsed-time check, and CSRF protection. Failed submissions look identical to successes (303 → `#thanks`) so spammers don't iterate.
- Every comment lands as **unapproved**. Approve or delete from `/admin/comments`. Approved comments appear publicly on the post page; nobody else sees the email address (it's stored, never rendered).
- Deleting a post cascades to its comments via the schema's `ON DELETE CASCADE`.
```

- [ ] **Step 2: Manual end-to-end smoke**

Run the dev server (if not already running):

```bash
uv run python main.py
```

In a browser:

1. `http://127.0.0.1:8000/blog` — empty state.
2. Sign into `/admin`. Dashboard now lists "Manage blog posts" and "Moderate comments".
3. **Manage blog posts → + New post.** Write a title and Markdown body. Leave slug blank. Save as draft (unchecked). `/blog` still empty. Visit `/blog/{slug}` while signed in → renders with "Draft" warning.
4. Sign out (footer logout). Visit the same `/blog/{slug}` → 404.
5. Sign in. Edit the post, check **Published**, save. `/blog` shows it. `/blog/{slug}` no longer flagged as draft.
6. **Open in incognito** (no session). Submit a comment. Land on `#thanks` banner. Submit a second comment too fast (rapid second submission within 3s) — also lands on `#thanks`, but the comment isn't actually saved.
7. Back in your normal browser, **/admin/comments** — your real comment is in Pending. Approve it. Refresh the public post page → comment now visible.
8. From `/admin/comments`, delete the comment. Refresh public page → gone.
9. From `/admin/posts`, delete the post. `/blog` empty again. (`/admin/comments` queue also empty — cascade.)

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: README — blog + comment moderation flow"
```

---

## Self-review notes

- **Spec coverage**:
  - Anonymous + admin moderation → Tasks 5 (form), 7 (queue + approve)
  - Honeypot + min-elapsed silent-reject → Task 5
  - Draft/published with `published_at` semantics → Task 6 (`post_create`, `post_update`, `post_publish_toggle`)
  - Pretty slugs + auto-gen + conflict suffix + edit-self exception → Task 3 helpers + Task 6 routes
  - Excerpt + Markdown body → Task 6 form + Task 5 rendering via shared helper
  - Markdown helper extraction → Task 1
  - "Drafts visible to admin" rule → Task 4 (initial route) and respected by Task 5's POST guard
  - Public nav adds Blog → Task 4
  - Cascade delete of comments → Task 2 schema (`ON DELETE CASCADE`) + Task 6 test asserting it
  - 80 passing tests by Task 7
- **Symbol consistency check**:
  - `render_markdown` in `backend/markdown.py` (not `_render_markdown`) — matched in `routes/public.py` (Task 1) and `routes/blog.py` (Tasks 4, 5).
  - `slugify` and `unique_slug` in `backend/blog_utils.py` — matched in `routes/admin.py` posts handlers (Task 6).
  - `MIN_ELAPSED_SECONDS`, `SESSION_KEY_FORM_TS`, `MAX_BODY_LEN`, `MAX_NAME_LEN`, `MAX_EMAIL_LEN`, `EMAIL_RE` defined once at the top of `routes/blog.py` (Task 5) — referenced by tests via `monkeypatch.setattr(blog_routes, "MIN_ELAPSED_SECONDS", 0)`.
  - `_silent_reject(slug)` returns the same 303 → `#thanks` as the success path, ensuring indistinguishability per spec.
  - The `requires_admin` / `requires_admin_post` deps reused from the existing `routes/admin.py` (no changes needed); `current_user` reused from `backend/auth.py`.
- **No placeholders**: every code block in this plan is the full code, every command shows its expected outcome.
