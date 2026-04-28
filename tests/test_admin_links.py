from sqlalchemy import select

from backend.models import Link


def test_create_edit_delete_link(signed_in_client, get_csrf, db_factory_with_seed):
    csrf = get_csrf("/admin/links/new")
    r = signed_in_client.post(
        "/admin/links/new",
        data={"csrf": csrf, "label": "GitHub", "url": "https://github.com/x", "position": "0"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    with db_factory_with_seed() as db:
        link = db.scalar(select(Link).where(Link.label == "GitHub"))
        assert link is not None
        lid = link.id

    csrf = get_csrf(f"/admin/links/{lid}")
    r = signed_in_client.post(
        f"/admin/links/{lid}",
        data={
            "csrf": csrf,
            "label": "Github (lowercase)",
            "url": "https://github.com/x",
            "position": "1",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    with db_factory_with_seed() as db:
        link = db.scalar(select(Link).where(Link.id == lid))
        assert link.label == "Github (lowercase)"
        assert link.position == 1

    csrf = get_csrf("/admin/links")
    r = signed_in_client.post(
        f"/admin/links/{lid}/delete",
        data={"csrf": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303
    with db_factory_with_seed() as db:
        assert db.scalar(select(Link).where(Link.id == lid)) is None


def test_public_contact_reflects_link_changes(signed_in_client, client, get_csrf):
    csrf = get_csrf("/admin/links/new")
    signed_in_client.post(
        "/admin/links/new",
        data={"csrf": csrf, "label": "Email", "url": "mailto:x@example.com", "position": "0"},
        follow_redirects=False,
    )
    # The public site is now a SPA; verify via the JSON API instead of HTML.
    r = client.get("/api/links")
    rows = r.json()
    labels = {l["label"]: l["url"] for l in rows}
    assert labels.get("Email") == "mailto:x@example.com"
