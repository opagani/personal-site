"""JSON API for the public SPA frontend.

Absorbs the data shapes that routes/public.py and routes/blog.py used to
render as HTML. The /api/blog/posts/{slug}/comments POST handler keeps the
exact anti-spam contract from the old form route (honeypot + min-elapsed
silent-reject + CSRF).
"""

import re
import time
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.auth import current_user, ensure_csrf_token, verify_csrf
from backend.db import get_db
from backend.markdown import render_markdown
from backend.models import Comment, Link, Post, Project, ResumeMeta, SiteMeta

ROOT = Path(__file__).resolve().parent.parent.parent

# Anti-spam tunables (test-overridable via monkeypatch)
MIN_ELAPSED_SECONDS = 3
MAX_NAME_LEN = 80
MAX_EMAIL_LEN = 120
MAX_BODY_LEN = 4000
MIN_BODY_LEN = 1
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
SESSION_KEY_FORM_TS = "comment_form_ts"

router = APIRouter(prefix="/api")


def _resume_pdf_available(rm: ResumeMeta | None) -> bool:
    if rm is None or not rm.pdf_path:
        return False
    if not rm.pdf_path.startswith("/static/"):
        return False
    rel = rm.pdf_path[len("/static/") :]
    return (ROOT / "frontend" / "static" / rel).is_file()


def _record_form_render(request: Request, slug: str) -> None:
    request.session[SESSION_KEY_FORM_TS] = {"slug": slug, "ts": int(time.time())}


def _elapsed_too_short(request: Request, slug: str) -> bool:
    info = request.session.get(SESSION_KEY_FORM_TS)
    if not info or info.get("slug") != slug:
        return True
    return (int(time.time()) - int(info.get("ts", 0))) < MIN_ELAPSED_SECONDS


@router.get("/site")
def get_site(db: Session = Depends(get_db)):
    sm = db.scalar(select(SiteMeta).where(SiteMeta.id == 1))
    if sm is None:
        raise HTTPException(404, detail="Site not configured")
    return {
        "name": sm.name,
        "headline": sm.headline,
        "bio": sm.bio,
        "avatar_url": sm.avatar_url,
    }


@router.get("/projects")
def list_projects(db: Session = Depends(get_db)):
    rows = db.scalars(select(Project).order_by(Project.position, Project.id)).all()
    return [
        {
            "id": p.id,
            "title": p.title,
            "description": p.description,
            "link": p.link,
            "position": p.position,
        }
        for p in rows
    ]


@router.get("/links")
def list_links(db: Session = Depends(get_db)):
    rows = db.scalars(select(Link).order_by(Link.position, Link.id)).all()
    return [
        {"id": l.id, "label": l.label, "url": l.url, "position": l.position}
        for l in rows
    ]


@router.get("/resume")
def get_resume(db: Session = Depends(get_db)):
    rm = db.scalar(select(ResumeMeta).where(ResumeMeta.id == 1))
    if rm is None:
        raise HTTPException(404, detail="Resume not configured")
    return {
        "summary_html": render_markdown(rm.summary),
        "pdf_path": rm.pdf_path,
        "pdf_available": _resume_pdf_available(rm),
    }


@router.get("/blog/posts")
def list_blog_posts(db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Post)
        .where(Post.published.is_(True))
        .order_by(Post.published_at.desc(), Post.id.desc())
    ).all()
    return [
        {
            "slug": p.slug,
            "title": p.title,
            "excerpt": p.excerpt,
            "published_at": p.published_at.isoformat() if p.published_at else None,
        }
        for p in rows
    ]


@router.get("/blog/posts/{slug}")
def get_blog_post(slug: str, request: Request, db: Session = Depends(get_db)):
    post = db.scalar(select(Post).where(Post.slug == slug))
    if post is None:
        raise HTTPException(404)
    if not post.published and current_user(request, db) is None:
        raise HTTPException(404)

    _record_form_render(request, slug)

    comments = db.scalars(
        select(Comment)
        .where(Comment.post_id == post.id, Comment.approved.is_(True))
        .order_by(Comment.created_at.asc(), Comment.id.asc())
    ).all()

    return {
        "slug": post.slug,
        "title": post.title,
        "published": post.published,
        "published_at": post.published_at.isoformat() if post.published_at else None,
        "body_html": render_markdown(post.body_md),
        "comment_form_token": ensure_csrf_token(request),
        "comments": [
            {
                "author_name": c.author_name,
                "body": c.body,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in comments
        ],
    }


@router.post("/blog/posts/{slug}/comments")
def submit_comment(
    slug: str,
    request: Request,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    csrf = (payload.get("csrf") or "").strip()
    verify_csrf(request, csrf)

    post = db.scalar(select(Post).where(Post.slug == slug))
    if post is None:
        raise HTTPException(404)
    if not post.published and current_user(request, db) is None:
        raise HTTPException(404)

    if (payload.get("url") or "").strip():
        return {"ok": True}
    if _elapsed_too_short(request, slug):
        return {"ok": True}

    name = (payload.get("author_name") or "").strip()
    email = (payload.get("author_email") or "").strip()
    body = (payload.get("body") or "").strip()

    errors: list[str] = []
    if not (1 <= len(name) <= MAX_NAME_LEN):
        errors.append(f"Name must be 1–{MAX_NAME_LEN} characters.")
    if not (5 <= len(email) <= MAX_EMAIL_LEN) or not EMAIL_RE.fullmatch(email):
        errors.append("Enter a valid email address.")
    if not (MIN_BODY_LEN <= len(body) <= MAX_BODY_LEN):
        errors.append(f"Comment must be {MIN_BODY_LEN}–{MAX_BODY_LEN} characters.")

    if errors:
        raise HTTPException(status_code=422, detail=errors)

    db.add(Comment(
        post_id=post.id,
        author_name=name,
        author_email=email,
        body=body,
    ))
    db.commit()
    return {"ok": True}
