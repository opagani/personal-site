from pathlib import Path


def _spa_index_path():
    return Path(__file__).resolve().parent.parent / "frontend-spa" / "dist" / "index.html"


def _ensure_spa_stub():
    """Write a deterministic stub index.html if the real build hasn't run.
    The actual prod build replaces this; tests just need *something* there."""
    p = _spa_index_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.is_file():
        p.write_text(
            "<!doctype html><html><body><div id='root'>SPA-STUB</div></body></html>",
            encoding="utf-8",
        )


def test_root_serves_spa_index_html(client):
    _ensure_spa_stub()
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "root" in r.text


def test_unknown_client_route_serves_spa_index_html(client):
    _ensure_spa_stub()
    r = client.get("/blog/some-slug")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")


def test_api_paths_are_not_swallowed(client):
    r = client.get("/api/no-such-endpoint")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")


def test_admin_login_still_serves_html(client):
    r = client.get("/admin/login")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "Admin login" in r.text
