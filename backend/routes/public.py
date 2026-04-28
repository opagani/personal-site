from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.models import Link, Project, ResumeMeta, SiteMeta

ROOT = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=ROOT / "frontend" / "templates")

router = APIRouter()


def _site(db: Session) -> SiteMeta | None:
    return db.scalar(select(SiteMeta).where(SiteMeta.id == 1))


@router.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request,
        "public/home.html",
        {"site": _site(db), "current_page": "home"},
    )


@router.get("/projects")
def projects(request: Request, db: Session = Depends(get_db)):
    rows = db.scalars(select(Project).order_by(Project.position, Project.id)).all()
    return templates.TemplateResponse(
        request,
        "public/projects.html",
        {"site": _site(db), "projects": rows, "current_page": "projects"},
    )


@router.get("/contact")
def contact(request: Request, db: Session = Depends(get_db)):
    rows = db.scalars(select(Link).order_by(Link.position, Link.id)).all()
    return templates.TemplateResponse(
        request,
        "public/contact.html",
        {"site": _site(db), "links": rows, "current_page": "contact"},
    )


@router.get("/resume")
def resume(request: Request, db: Session = Depends(get_db)):
    site = _site(db)
    rmeta = db.scalar(select(ResumeMeta).where(ResumeMeta.id == 1))
    pdf_path_on_disk = ROOT / "frontend" / "static" / "resume.pdf"
    pdf_available = bool(rmeta and rmeta.pdf_path) and pdf_path_on_disk.is_file()
    return templates.TemplateResponse(
        request,
        "public/resume.html",
        {
            "site": site,
            "resume": rmeta,
            "resume_pdf_available": pdf_available,
            "current_page": "resume",
        },
    )
