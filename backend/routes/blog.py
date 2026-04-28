from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.auth import current_user
from backend.db import get_db
from backend.markdown import render_markdown
from backend.models import Post, SiteMeta

ROOT = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=ROOT / "frontend" / "templates")

router = APIRouter()


def _site_meta(db: Session) -> SiteMeta | None:
    return db.scalar(select(SiteMeta).where(SiteMeta.id == 1))


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
    body_html = render_markdown(post.body_md)
    return templates.TemplateResponse(
        request,
        "public/blog_post.html",
        {
            "site": _site_meta(db),
            "post": post,
            "body_html": body_html,
            "current_page": "blog",
        },
    )
