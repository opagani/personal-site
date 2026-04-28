import re
import time
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.auth import (
    csrf_form_field,
    current_user,
    ensure_csrf_token,
    verify_csrf,
)
from backend.db import get_db
from backend.markdown import render_markdown
from backend.models import Comment, Post, SiteMeta

ROOT = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=ROOT / "frontend" / "templates")

router = APIRouter()

# Anti-spam tunables (test-overridable)
MIN_ELAPSED_SECONDS = 3
MAX_NAME_LEN = 80
MAX_EMAIL_LEN = 120
MAX_BODY_LEN = 4000
MIN_BODY_LEN = 1
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
SESSION_KEY_FORM_TS = "comment_form_ts"


def _site_meta(db: Session) -> SiteMeta | None:
    return db.scalar(select(SiteMeta).where(SiteMeta.id == 1))


def _record_form_render(request: Request, slug: str) -> None:
    request.session[SESSION_KEY_FORM_TS] = {"slug": slug, "ts": int(time.time())}


def _elapsed_too_short(request: Request, slug: str) -> bool:
    info = request.session.get(SESSION_KEY_FORM_TS)
    if not info or info.get("slug") != slug:
        return True
    return (int(time.time()) - int(info.get("ts", 0))) < MIN_ELAPSED_SECONDS


def _silent_reject(slug: str) -> RedirectResponse:
    """Indistinguishable from a real success: 303 → #thanks, no DB write."""
    return RedirectResponse(url=f"/blog/{slug}#thanks", status_code=303)


def _render_post(
    request: Request,
    db: Session,
    post: Post,
    *,
    form: dict | None = None,
    errors: list[str] | None = None,
):
    approved_comments = db.scalars(
        select(Comment)
        .where(Comment.post_id == post.id, Comment.approved.is_(True))
        .order_by(Comment.created_at.asc(), Comment.id.asc())
    ).all()
    return templates.TemplateResponse(
        request,
        "public/blog_post.html",
        {
            "site": _site_meta(db),
            "post": post,
            "body_html": render_markdown(post.body_md),
            "comments": approved_comments,
            "csrf_token": ensure_csrf_token(request),
            "form": form or {"author_name": "", "author_email": "", "body": ""},
            "errors": errors or [],
            "current_page": "blog",
        },
        status_code=200,
    )


@router.get("/blog")
def blog_list(request: Request, db: Session = Depends(get_db)):
    posts = db.scalars(
        select(Post)
        .where(Post.published.is_(True))
        .order_by(Post.published_at.desc(), Post.id.desc())
    ).all()
    return templates.TemplateResponse(
        request,
        "public/blog_list.html",
        {"site": _site_meta(db), "posts": posts, "current_page": "blog"},
    )


@router.get("/blog/{slug}")
def blog_post(slug: str, request: Request, db: Session = Depends(get_db)):
    post = db.scalar(select(Post).where(Post.slug == slug))
    if post is None:
        raise HTTPException(status_code=404)
    if not post.published and current_user(request, db) is None:
        raise HTTPException(status_code=404)
    _record_form_render(request, slug)
    return _render_post(request, db, post)


@router.post("/blog/{slug}/comments")
def submit_comment(
    slug: str,
    request: Request,
    db: Session = Depends(get_db),
    csrf: str = Depends(csrf_form_field),
    url: str = Form(""),
    author_name: str = Form(""),
    author_email: str = Form(""),
    body: str = Form(""),
):
    verify_csrf(request, csrf)

    post = db.scalar(select(Post).where(Post.slug == slug))
    if post is None:
        raise HTTPException(status_code=404)
    if not post.published and current_user(request, db) is None:
        raise HTTPException(status_code=404)

    if url.strip():
        return _silent_reject(slug)
    if _elapsed_too_short(request, slug):
        return _silent_reject(slug)

    name = author_name.strip()
    email = author_email.strip()
    body_clean = body.strip()
    errors: list[str] = []
    if not (1 <= len(name) <= MAX_NAME_LEN):
        errors.append(f"Name must be 1–{MAX_NAME_LEN} characters.")
    if not (5 <= len(email) <= MAX_EMAIL_LEN) or not EMAIL_RE.fullmatch(email):
        errors.append("Enter a valid email address.")
    if not (MIN_BODY_LEN <= len(body_clean) <= MAX_BODY_LEN):
        errors.append(f"Comment must be {MIN_BODY_LEN}–{MAX_BODY_LEN} characters.")

    if errors:
        return _render_post(
            request, db, post,
            form={"author_name": name, "author_email": email, "body": body_clean},
            errors=errors,
        )

    db.add(Comment(
        post_id=post.id,
        author_name=name,
        author_email=email,
        body=body_clean,
    ))
    db.commit()
    return RedirectResponse(url=f"/blog/{slug}#thanks", status_code=303)
