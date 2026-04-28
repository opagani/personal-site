"""Public-route tests use the shared `client` fixture from conftest.py and
add their own seeded projects/links via the underlying db_factory."""

import pytest

from backend.models import Link, Project


@pytest.fixture
def client(client, db_factory):
    """Extend the shared client fixture with a seeded project + link."""
    Session = db_factory
    with Session() as s:
        s.add(
            Project(
                title="Note G",
                description="The first algorithm.",
                link="https://example.com",
                position=0,
            )
        )
        s.add(Link(label="GitHub", url="https://github.com/ada", position=0))
        s.commit()
    return client


def test_home_renders_site_meta(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Ada Lovelace" in r.text
    assert "Mathematician" in r.text
    assert 'aria-current="page"' in r.text


def test_home_uses_seeded_bio(client):
    r = client.get("/")
    assert "Notes." in r.text


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
    assert "Summary text." in r.text
    assert "PDF not yet uploaded" in r.text


def test_static_styles_served(client):
    r = client.get("/static/styles.css")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/css")
