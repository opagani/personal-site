import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Form, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import User

SESSION_KEY_USER = "user_id"
SESSION_KEY_CSRF = "csrf"
CSRF_FIELD = "csrf"

_ph = PasswordHasher()


def hash_password(plain: str) -> str:
    return _ph.hash(plain)


def verify_password(stored_hash: str, plain: str) -> bool:
    try:
        return _ph.verify(stored_hash, plain)
    except VerifyMismatchError:
        return False


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def ensure_csrf_token(request: Request) -> str:
    token = request.session.get(SESSION_KEY_CSRF)
    if not token:
        token = generate_csrf_token()
        request.session[SESSION_KEY_CSRF] = token
    return token


def rotate_csrf_token(request: Request) -> str:
    token = generate_csrf_token()
    request.session[SESSION_KEY_CSRF] = token
    return token


def verify_csrf(request: Request, submitted: str) -> None:
    expected = request.session.get(SESSION_KEY_CSRF)
    if not expected or not submitted or not secrets.compare_digest(expected, submitted):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF check failed")


def current_user(request: Request, db: Session) -> User | None:
    uid = request.session.get(SESSION_KEY_USER)
    if uid is None:
        return None
    return db.scalar(select(User).where(User.id == uid))


def csrf_form_field(csrf: str = Form(..., alias=CSRF_FIELD)) -> str:
    return csrf
