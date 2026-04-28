from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.db import Base
from backend.models import User, SiteMeta, Project, Link, ResumeMeta


def _fresh_engine():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return engine


def test_create_all_creates_every_table():
    _fresh_engine()
    expected = {"users", "site_meta", "projects", "links", "resume_meta"}
    assert expected.issubset(set(Base.metadata.tables.keys()))


def test_can_insert_and_query_each_model():
    engine = _fresh_engine()
    with Session(engine) as s:
        s.add(User(username="admin", password_hash="x"))
        s.add(SiteMeta(id=1, name="N", headline="H", bio="B"))
        s.add(Project(title="T", description="D", position=0))
        s.add(Link(label="GitHub", url="https://example.com", position=0))
        s.add(ResumeMeta(id=1, summary="S"))
        s.commit()

        assert s.query(User).count() == 1
        assert s.query(SiteMeta).one().name == "N"
        assert s.query(Project).one().title == "T"
        assert s.query(Link).one().label == "GitHub"
        assert s.query(ResumeMeta).one().summary == "S"


def test_user_username_is_unique():
    import sqlalchemy.exc
    engine = _fresh_engine()
    with Session(engine) as s:
        s.add(User(username="admin", password_hash="a"))
        s.commit()
        s.add(User(username="admin", password_hash="b"))
        try:
            s.commit()
            raised = False
        except sqlalchemy.exc.IntegrityError:
            raised = True
    assert raised


def test_timestamps_default_to_now_for_user_and_project():
    engine = _fresh_engine()
    with Session(engine) as s:
        u = User(username="u", password_hash="x")
        p = Project(title="t", description="d", position=0)
        s.add_all([u, p])
        s.commit()
        s.refresh(u)
        s.refresh(p)
        assert isinstance(u.created_at, datetime)
        assert isinstance(p.created_at, datetime)
        assert isinstance(p.updated_at, datetime)
