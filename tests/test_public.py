"""SPA-era public tests. The public site is now a React SPA; the backend
serves /api/* (covered in test_api.py) and a catch-all that returns the
built SPA's index.html (covered in test_spa_fallback.py). This file keeps
the small set of cross-cutting checks that don't fit naturally into either."""


def test_static_styles_served(client):
    # frontend/static/styles.css is now used by the admin templates only,
    # but the mount must keep working.
    r = client.get("/static/styles.css")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/css")
