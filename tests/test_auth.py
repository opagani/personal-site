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
