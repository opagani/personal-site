from pathlib import Path
from types import SimpleNamespace

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
from backend.models import Project, ResumeMeta, SiteMeta, User

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


# --- site_meta editor ---


@router.get("/site")
def site_form(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(requires_admin),
):
    return templates.TemplateResponse(
        request,
        "admin/site_form.html",
        {
            "site": _site_meta(db),
            "user": user,
            "csrf_token": ensure_csrf_token(request),
            "current_page": None,
        },
    )


@router.post("/site")
def site_save(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(requires_admin_post),
    name: str = Form(...),
    headline: str = Form(...),
    bio: str = Form(...),
    avatar_url: str = Form(""),
):
    sm = db.scalar(select(SiteMeta).where(SiteMeta.id == 1))
    sm.name = name
    sm.headline = headline
    sm.bio = bio
    sm.avatar_url = avatar_url or None
    db.commit()
    return RedirectResponse(url="/admin/site", status_code=303)


# --- resume_meta editor ---


@router.get("/resume")
def resume_form(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(requires_admin),
):
    rm = db.scalar(select(ResumeMeta).where(ResumeMeta.id == 1))
    return templates.TemplateResponse(
        request,
        "admin/resume_form.html",
        {
            "site": _site_meta(db),
            "resume": rm,
            "user": user,
            "csrf_token": ensure_csrf_token(request),
            "current_page": None,
        },
    )


@router.post("/resume")
def resume_save(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(requires_admin_post),
    summary: str = Form(...),
    pdf_path: str = Form(""),
):
    rm = db.scalar(select(ResumeMeta).where(ResumeMeta.id == 1))
    rm.summary = summary
    rm.pdf_path = pdf_path or None
    db.commit()
    return RedirectResponse(url="/admin/resume", status_code=303)


# --- projects CRUD ---


@router.get("/projects")
def projects_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(requires_admin),
):
    rows = db.scalars(select(Project).order_by(Project.position, Project.id)).all()
    return templates.TemplateResponse(
        request,
        "admin/project_list.html",
        {
            "site": _site_meta(db),
            "projects": rows,
            "user": user,
            "csrf_token": ensure_csrf_token(request),
            "current_page": None,
        },
    )


@router.get("/projects/new")
def project_new_form(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(requires_admin),
):
    blank = SimpleNamespace(id=None, title="", description="", link="", position=0)
    return templates.TemplateResponse(
        request,
        "admin/project_form.html",
        {
            "site": _site_meta(db),
            "project": blank,
            "is_new": True,
            "user": user,
            "csrf_token": ensure_csrf_token(request),
            "current_page": None,
        },
    )


@router.post("/projects/new")
def project_create(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(requires_admin_post),
    title: str = Form(...),
    description: str = Form(...),
    link: str = Form(""),
    position: int = Form(0),
):
    db.add(Project(title=title, description=description, link=link or None, position=position))
    db.commit()
    return RedirectResponse(url="/admin/projects", status_code=303)


@router.get("/projects/{project_id}")
def project_edit_form(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(requires_admin),
):
    p = db.scalar(select(Project).where(Project.id == project_id))
    if p is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return templates.TemplateResponse(
        request,
        "admin/project_form.html",
        {
            "site": _site_meta(db),
            "project": p,
            "is_new": False,
            "user": user,
            "csrf_token": ensure_csrf_token(request),
            "current_page": None,
        },
    )


@router.post("/projects/{project_id}")
def project_update(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(requires_admin_post),
    title: str = Form(...),
    description: str = Form(...),
    link: str = Form(""),
    position: int = Form(0),
):
    p = db.scalar(select(Project).where(Project.id == project_id))
    if p is None:
        raise HTTPException(status_code=404, detail="Project not found")
    p.title = title
    p.description = description
    p.link = link or None
    p.position = position
    db.commit()
    return RedirectResponse(url="/admin/projects", status_code=303)


@router.post("/projects/{project_id}/delete")
def project_delete(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(requires_admin_post),
):
    p = db.scalar(select(Project).where(Project.id == project_id))
    if p is None:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete(p)
    db.commit()
    return RedirectResponse(url="/admin/projects", status_code=303)
