"""Dump and load site content as JSON.

Used to migrate content from one DB (typically local dev) to another
(typically a freshly-deployed production DB). Excludes auth tables (`users`)
and the moderation queue (`comments`) — those are intentionally not portable.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.models import Link, Post, Project, ResumeMeta, SiteMeta


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _parse_iso(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


def dump_content(db: Session) -> dict:
    sm = db.scalar(select(SiteMeta).where(SiteMeta.id == 1))
    rm = db.scalar(select(ResumeMeta).where(ResumeMeta.id == 1))
    projects = db.scalars(select(Project).order_by(Project.position, Project.id)).all()
    links = db.scalars(select(Link).order_by(Link.position, Link.id)).all()
    posts = db.scalars(select(Post).order_by(Post.published_at.desc(), Post.id)).all()

    return {
        "version": 1,
        "site_meta": {
            "name": sm.name,
            "headline": sm.headline,
            "bio": sm.bio,
            "avatar_url": sm.avatar_url,
        } if sm else None,
        "resume_meta": {
            "summary": rm.summary,
            "pdf_path": rm.pdf_path,
        } if rm else None,
        "projects": [
            {
                "title": p.title,
                "description": p.description,
                "link": p.link,
                "position": p.position,
            }
            for p in projects
        ],
        "links": [
            {"label": l.label, "url": l.url, "position": l.position}
            for l in links
        ],
        "posts": [
            {
                "slug": p.slug,
                "title": p.title,
                "excerpt": p.excerpt,
                "body_md": p.body_md,
                "published": p.published,
                "published_at": _iso(p.published_at),
            }
            for p in posts
        ],
    }


def load_content(
    db: Session,
    fixture: dict | Path,
    *,
    only_if_empty: bool = False,
) -> dict:
    """Sync the DB to match the fixture. Returns counts of what was written.

    Singletons (site_meta, resume_meta) are upserted. List tables (projects,
    links, posts) are *replaced* — anything not in the fixture is removed.

    `only_if_empty` skips the load entirely if any projects already exist —
    useful for one-off bootstraps where you don't want to clobber subsequent
    admin edits. The lifespan auto-loader does NOT use this flag (the JSON
    is the source of truth, always).
    """
    if isinstance(fixture, Path):
        fixture = json.loads(fixture.read_text())

    if only_if_empty:
        project_count = db.scalar(select(func.count(Project.id))) or 0
        if project_count > 0:
            return {"skipped": True, "reason": "DB already has projects"}

    counts = {"projects": 0, "links": 0, "posts": 0, "site_meta": 0, "resume_meta": 0}

    # Singletons: upsert.
    sm_data = fixture.get("site_meta")
    if sm_data:
        sm = db.scalar(select(SiteMeta).where(SiteMeta.id == 1))
        if sm is None:
            sm = SiteMeta(id=1, **sm_data)
            db.add(sm)
        else:
            sm.name = sm_data["name"]
            sm.headline = sm_data["headline"]
            sm.bio = sm_data["bio"]
            sm.avatar_url = sm_data.get("avatar_url")
        counts["site_meta"] = 1

    rm_data = fixture.get("resume_meta")
    if rm_data:
        rm = db.scalar(select(ResumeMeta).where(ResumeMeta.id == 1))
        if rm is None:
            rm = ResumeMeta(id=1, **rm_data)
            db.add(rm)
        else:
            rm.summary = rm_data["summary"]
            rm.pdf_path = rm_data.get("pdf_path")
        counts["resume_meta"] = 1

    # Lists: delete-and-insert for true sync. Comments cascade with posts via FK.
    db.execute(delete(Post))
    db.execute(delete(Link))
    db.execute(delete(Project))
    db.flush()

    for project in fixture.get("projects", []):
        db.add(Project(**project))
        counts["projects"] += 1

    for link in fixture.get("links", []):
        db.add(Link(**link))
        counts["links"] += 1

    for post in fixture.get("posts", []):
        db.add(Post(
            slug=post["slug"],
            title=post["title"],
            excerpt=post.get("excerpt"),
            body_md=post["body_md"],
            published=post.get("published", False),
            published_at=_parse_iso(post.get("published_at")),
        ))
        counts["posts"] += 1

    db.commit()
    return counts
