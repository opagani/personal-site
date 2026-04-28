import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import app
from backend.auth import hash_password
from backend.db import Base, get_db
from backend.models import ResumeMeta, SiteMeta, User


@pytest.fixture
def db_factory():
    """Yield a sessionmaker bound to a fresh shared in-memory SQLite DB.

    Seeds the singletons + an admin user (`admin` / `secret`).
    """
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    with Session() as s:
        s.add(SiteMeta(id=1, name="Ada Lovelace", headline="Mathematician", bio="Notes."))
        s.add(ResumeMeta(id=1, summary="Summary text.", pdf_path="/static/resume.pdf"))
        s.add(User(username="admin", password_hash=hash_password("secret")))
        s.commit()

    return Session


@pytest.fixture
def client(db_factory):
    Session = db_factory

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _extract_csrf(html: str) -> str:
    m = re.search(r'name="csrf"\s+value="([^"]+)"', html)
    assert m, "CSRF token not found in form HTML"
    return m.group(1)


@pytest.fixture
def signed_in_client(client):
    r = client.get("/admin/login")
    csrf = _extract_csrf(r.text)
    r = client.post(
        "/admin/login",
        data={"username": "admin", "password": "secret", "csrf": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    return client


@pytest.fixture
def get_csrf(signed_in_client):
    def _get(path: str) -> str:
        r = signed_in_client.get(path)
        assert r.status_code == 200, f"GET {path} returned {r.status_code}"
        return _extract_csrf(r.text)

    return _get


@pytest.fixture
def db_factory_with_seed(db_factory):
    return db_factory
