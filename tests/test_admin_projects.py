from sqlalchemy import select

from backend.models import Project


def test_admin_projects_list_when_empty(signed_in_client):
    r = signed_in_client.get("/admin/projects")
    assert r.status_code == 200
    assert "No projects yet" in r.text or "Add" in r.text or "+ New project" in r.text


def test_create_project(signed_in_client, get_csrf, db_factory_with_seed):
    csrf = get_csrf("/admin/projects/new")
    r = signed_in_client.post(
        "/admin/projects/new",
        data={
            "csrf": csrf,
            "title": "Note G",
            "description": "First algorithm.",
            "link": "https://example.com",
            "position": "0",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"].endswith("/admin/projects")
    with db_factory_with_seed() as db:
        p = db.scalar(select(Project).where(Project.title == "Note G"))
        assert p is not None
        assert p.description == "First algorithm."


def test_edit_project(signed_in_client, get_csrf, db_factory_with_seed):
    csrf = get_csrf("/admin/projects/new")
    signed_in_client.post(
        "/admin/projects/new",
        data={"csrf": csrf, "title": "Initial", "description": "d", "link": "", "position": "0"},
        follow_redirects=False,
    )
    with db_factory_with_seed() as db:
        pid = db.scalar(select(Project.id).where(Project.title == "Initial"))

    csrf = get_csrf(f"/admin/projects/{pid}")
    r = signed_in_client.post(
        f"/admin/projects/{pid}",
        data={"csrf": csrf, "title": "Renamed", "description": "d2", "link": "", "position": "5"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    with db_factory_with_seed() as db:
        p = db.scalar(select(Project).where(Project.id == pid))
        assert p.title == "Renamed"
        assert p.description == "d2"
        assert p.position == 5


def test_delete_project(signed_in_client, get_csrf, db_factory_with_seed):
    csrf = get_csrf("/admin/projects/new")
    signed_in_client.post(
        "/admin/projects/new",
        data={"csrf": csrf, "title": "Doomed", "description": "d", "link": "", "position": "0"},
        follow_redirects=False,
    )
    with db_factory_with_seed() as db:
        pid = db.scalar(select(Project.id).where(Project.title == "Doomed"))

    csrf = get_csrf("/admin/projects")
    r = signed_in_client.post(
        f"/admin/projects/{pid}/delete",
        data={"csrf": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303
    with db_factory_with_seed() as db:
        assert db.scalar(select(Project).where(Project.id == pid)) is None


def test_public_projects_reflects_db_changes(signed_in_client, client, get_csrf):
    csrf = get_csrf("/admin/projects/new")
    signed_in_client.post(
        "/admin/projects/new",
        data={
            "csrf": csrf,
            "title": "Visible",
            "description": "Public copy.",
            "link": "",
            "position": "0",
        },
        follow_redirects=False,
    )
    # SPA-era: verify via JSON API.
    r = client.get("/api/projects")
    titles = {p["title"]: p["description"] for p in r.json()}
    assert titles.get("Visible") == "Public copy."


def test_get_unknown_project_returns_404(signed_in_client):
    r = signed_in_client.get("/admin/projects/9999")
    assert r.status_code == 404
