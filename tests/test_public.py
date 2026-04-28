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


def test_resume_renders_summary_and_handles_missing_pdf(client, db_factory):
    # Clear pdf_path on the seeded singleton so the "missing PDF" branch is
    # exercised deterministically regardless of whether a real resume.pdf
    # exists in frontend/static.
    from backend.models import ResumeMeta

    Session = db_factory
    with Session() as s:
        rm = s.get(ResumeMeta, 1)
        rm.pdf_path = None
        s.commit()

    r = client.get("/resume")
    assert r.status_code == 200
    assert "Summary text." in r.text
    assert "PDF not yet uploaded" in r.text


def test_static_styles_served(client):
    r = client.get("/static/styles.css")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/css")


def test_projects_paginates_when_more_than_per_page(client, db_factory):
    Session = db_factory
    with Session() as s:
        for i in range(14):  # plus the existing 1 → 15 total → 2 pages of 10
            s.add(Project(title=f"Extra-{i:02d}", description="x", position=100 + i))
        s.commit()

    # Page 1
    r = client.get("/projects")
    assert r.status_code == 200
    assert "?page=2" in r.text  # paginator link rendered

    # Page 2
    r = client.get("/projects?page=2")
    assert r.status_code == 200
    # At least one of the high-position items lives on page 2
    assert any(f"Extra-{i:02d}" in r.text for i in range(10, 14))


def test_projects_no_paginator_when_few(client):
    # Only the seeded "Note G" — 1 project, well under per_page → no paginator.
    r = client.get("/projects")
    assert r.status_code == 200
    assert "pagination" not in r.text
    assert "?page=" not in r.text
