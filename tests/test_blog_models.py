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
        assert loaded.published_at is None

        cs = s.scalars(select(Comment).where(Comment.post_id == p.id)).all()
        assert len(cs) == 1
        assert cs[0].approved is False


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
