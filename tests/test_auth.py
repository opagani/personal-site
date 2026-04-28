import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.auth import (
    CSRF_FIELD,
    SESSION_KEY_CSRF,
    SESSION_KEY_USER,
    generate_csrf_token,
    hash_password,
    verify_csrf,
    verify_password,
)


def _request_with_session(session: dict) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/admin/site",
        "headers": [],
        "session": session,
    }
    return Request(scope)


def test_hash_and_verify_round_trip():
    h = hash_password("hunter2")
    assert h != "hunter2"
    assert verify_password(h, "hunter2") is True
    assert verify_password(h, "wrong") is False


def test_generate_csrf_token_is_url_safe_and_random():
    a = generate_csrf_token()
    b = generate_csrf_token()
    assert a != b
    assert len(a) >= 32
    import re

    assert re.fullmatch(r"[A-Za-z0-9_-]+", a)


def test_verify_csrf_passes_on_match():
    session = {SESSION_KEY_CSRF: "abc"}
    req = _request_with_session(session)
    verify_csrf(req, submitted="abc")


def test_verify_csrf_raises_on_mismatch():
    session = {SESSION_KEY_CSRF: "abc"}
    req = _request_with_session(session)
    with pytest.raises(HTTPException) as exc:
        verify_csrf(req, submitted="zzz")
    assert exc.value.status_code == 403


def test_verify_csrf_raises_when_session_missing_token():
    req = _request_with_session({})
    with pytest.raises(HTTPException):
        verify_csrf(req, submitted="abc")


def test_session_key_constants_are_strings():
    assert isinstance(SESSION_KEY_USER, str)
    assert isinstance(SESSION_KEY_CSRF, str)
    assert CSRF_FIELD == "csrf"


# --- login / logout flow ---


def _extract_csrf_helper(html: str) -> str:
    import re

    m = re.search(r'name="csrf"\s+value="([^"]+)"', html)
    assert m
    return m.group(1)


def test_admin_unauthenticated_redirects_to_login(client):
    r = client.get("/admin", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].endswith("/admin/login")


def test_admin_login_get_serves_form_with_csrf(client):
    r = client.get("/admin/login")
    assert r.status_code == 200
    assert 'name="csrf"' in r.text
    assert 'name="username"' in r.text
    assert 'name="password"' in r.text


def test_admin_login_wrong_password_renders_error(client):
    r = client.get("/admin/login")
    csrf = _extract_csrf_helper(r.text)
    r = client.post(
        "/admin/login",
        data={"username": "admin", "password": "wrong", "csrf": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 200
    assert "Invalid" in r.text or "incorrect" in r.text.lower()


def test_admin_login_correct_redirects_to_dashboard(client):
    r = client.get("/admin/login")
    csrf = _extract_csrf_helper(r.text)
    r = client.post(
        "/admin/login",
        data={"username": "admin", "password": "secret", "csrf": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"].endswith("/admin")


def test_admin_dashboard_when_signed_in(signed_in_client):
    r = signed_in_client.get("/admin")
    assert r.status_code == 200
    assert "Dashboard" in r.text or "admin" in r.text.lower()


def test_admin_logout_clears_session(signed_in_client):
    r = signed_in_client.get("/admin")
    csrf = _extract_csrf_helper(r.text)
    r = signed_in_client.post(
        "/admin/logout",
        data={"csrf": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303
    r = signed_in_client.get("/admin", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].endswith("/admin/login")


def test_login_post_without_csrf_is_rejected(client):
    r = client.post(
        "/admin/login",
        data={"username": "admin", "password": "secret"},
        follow_redirects=False,
    )
    assert r.status_code in (403, 422)
