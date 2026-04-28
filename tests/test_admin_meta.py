from sqlalchemy import select

from backend.models import ResumeMeta, SiteMeta


def test_get_admin_site_renders_prefilled_form(signed_in_client):
    r = signed_in_client.get("/admin/site")
    assert r.status_code == 200
    assert 'value="Ada Lovelace"' in r.text
    assert 'name="csrf"' in r.text


def test_post_admin_site_updates_db(signed_in_client, get_csrf, db_factory_with_seed):
    csrf = get_csrf("/admin/site")
    r = signed_in_client.post(
        "/admin/site",
        data={
            "csrf": csrf,
            "name": "Grace Hopper",
            "headline": "Rear Admiral, USN",
            "bio": "Compiler pioneer.",
            "avatar_url": "",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"].endswith("/admin/site")

    with db_factory_with_seed() as db:
        sm = db.scalar(select(SiteMeta).where(SiteMeta.id == 1))
        assert sm.name == "Grace Hopper"
        assert sm.headline == "Rear Admiral, USN"
        assert sm.avatar_url is None


def test_post_admin_site_without_csrf_is_403(signed_in_client):
    r = signed_in_client.post(
        "/admin/site",
        data={"name": "X", "headline": "Y", "bio": "Z", "avatar_url": ""},
        follow_redirects=False,
    )
    assert r.status_code in (403, 422)


def test_post_admin_resume_updates_db(signed_in_client, get_csrf, db_factory_with_seed):
    csrf = get_csrf("/admin/resume")
    r = signed_in_client.post(
        "/admin/resume",
        data={
            "csrf": csrf,
            "summary": "New summary.",
            "pdf_path": "/static/resume.pdf",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    with db_factory_with_seed() as db:
        rm = db.scalar(select(ResumeMeta).where(ResumeMeta.id == 1))
        assert rm.summary == "New summary."
