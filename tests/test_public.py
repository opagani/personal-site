import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import app
from backend.db import Base, get_db
from backend.models import Link, Project, ResumeMeta, SiteMeta


@pytest.fixture
def client():
    # StaticPool keeps a single in-memory DB shared across connections;
    # default SQLite pooling gives each connection its own empty :memory: DB.
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    with TestSession() as s:
        s.add(SiteMeta(id=1, name="Ada Lovelace", headline="Mathematician", bio="Notes."))
        s.add(ResumeMeta(id=1, summary="Long-form summary.", pdf_path="/static/resume.pdf"))
        s.add(Project(title="Note G", description="The first algorithm.", link="https://example.com", position=0))
        s.add(Link(label="GitHub", url="https://github.com/ada", position=0))
        s.commit()

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    # No `with`: skip lifespan so tests don't touch the real site.db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_home_renders_site_meta(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Ada Lovelace" in r.text
    assert "Mathematician" in r.text
    assert 'aria-current="page"' in r.text


def test_projects_renders_db_rows(client):
    r = client.get("/projects")
    assert r.status_code == 200
    assert "Note G" in r.text
    assert "The first algorithm." in r.text


def test_contact_renders_links(client):
    r = client.get("/contact")
    assert r.status_code == 200
    assert "GitHub" in r.text
    assert "https://github.com/ada" in r.text


def test_resume_renders_summary_and_handles_missing_pdf(client):
    r = client.get("/resume")
    assert r.status_code == 200
    assert "Long-form summary." in r.text
    assert "PDF not yet uploaded" in r.text


def test_static_styles_served(client):
    r = client.get("/static/styles.css")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/css")
