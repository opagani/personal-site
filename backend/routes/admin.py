from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.auth import (
    SESSION_KEY_USER,
    csrf_form_field,
    current_user,
    ensure_csrf_token,
    rotate_csrf_token,
    verify_csrf,
    verify_password,
)
from backend.db import get_db
from backend.models import SiteMeta, User

ROOT = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=ROOT / "frontend" / "templates")

router = APIRouter(prefix="/admin")


def _site_meta(db: Session) -> SiteMeta | None:
    return db.scalar(select(SiteMeta).where(SiteMeta.id == 1))


def requires_admin(request: Request, db: Session = Depends(get_db)) -> User:
    user = current_user(request, db)
    if user is None:
        raise HTTPException(status_code=303, headers={"location": "/admin/login"})
    return user


def requires_admin_post(
    request: Request,
    user: User = Depends(requires_admin),
    csrf: str = Depends(csrf_form_field),
) -> User:
    verify_csrf(request, csrf)
    return user


@router.get("/login")
def login_form(request: Request, db: Session = Depends(get_db), error: str | None = None):
    csrf_token = ensure_csrf_token(request)
    has_admin = db.scalar(select(User).limit(1)) is not None
    return templates.TemplateResponse(
        request,
        "admin/login.html",
        {
            "site": _site_meta(db),
            "csrf_token": csrf_token,
            "configured": has_admin,
            "error": error,
            "current_page": None,
        },
    )


@router.post("/login")
def login_submit(
    request: Request,
    db: Session = Depends(get_db),
    username: str = Form(...),
    password: str = Form(...),
    csrf: str = Depends(csrf_form_field),
):
    verify_csrf(request, csrf)
    user = db.scalar(select(User).where(User.username == username))
    if user is None or not verify_password(user.password_hash, password):
        csrf_token = ensure_csrf_token(request)
        has_admin = db.scalar(select(User).limit(1)) is not None
        return templates.TemplateResponse(
            request,
            "admin/login.html",
            {
                "site": _site_meta(db),
                "csrf_token": csrf_token,
                "configured": has_admin,
                "error": "Invalid username or password.",
                "current_page": None,
            },
            status_code=200,
        )

    request.session[SESSION_KEY_USER] = user.id
    rotate_csrf_token(request)
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/logout")
def logout(
    request: Request,
    user: User = Depends(requires_admin_post),
):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)


@router.get("")
@router.get("/")
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(requires_admin),
):
    return templates.TemplateResponse(
        request,
        "admin/dashboard.html",
        {
            "site": _site_meta(db),
            "user": user,
            "csrf_token": ensure_csrf_token(request),
            "current_page": None,
        },
    )
