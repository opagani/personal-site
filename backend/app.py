import logging
import secrets as _secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from backend.db import Base, SessionLocal, engine
from backend.models import ResumeMeta, SiteMeta, User
from backend.routes.admin import router as admin_router
from backend.routes.blog import router as blog_router
from backend.routes.public import router as public_router
from backend.settings import settings

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("portfolio")

DEFAULT_SITE = {
    "name": "Your Name",
    "headline": "Software engineer, builder, occasional writer.",
    "bio": (
        "Hi — I'm a software engineer who likes small, well-built things. "
        "This site is a quick portfolio of what I've worked on and how to reach me."
    ),
}
DEFAULT_RESUME = {
    "summary": (
        "A one-paragraph summary of your background, skills, and what you're looking "
        "for. The full resume is available as a PDF download below."
    ),
    "pdf_path": "/assets/resume.pdf",
}


def _seed_singletons(db: Session) -> None:
    if db.scalar(select(SiteMeta).where(SiteMeta.id == 1)) is None:
        db.add(SiteMeta(id=1, **DEFAULT_SITE))
    if db.scalar(select(ResumeMeta).where(ResumeMeta.id == 1)) is None:
        db.add(ResumeMeta(id=1, **DEFAULT_RESUME))
    db.commit()


def _migrate_pdf_paths(db: Session) -> None:
    """One-time: rewrite legacy pdf_path values from /static/ to /assets/.

    Railway's edge intercepts /static/* and never forwards to the origin, so
    any /static/X URL stored in the DB became unreachable. Idempotent — safe
    to run on every startup."""
    rm = db.scalar(select(ResumeMeta).where(ResumeMeta.id == 1))
    if rm and rm.pdf_path and rm.pdf_path.startswith("/static/"):
        rm.pdf_path = "/assets/" + rm.pdf_path[len("/static/") :]
        db.commit()


def _warn_if_no_admin(db: Session) -> None:
    if db.scalar(select(User).limit(1)) is None:
        log.warning("No admin user. Run: uv run python -m backend.cli create-admin")


def _resolve_secret_key() -> str:
    if settings.secret_key:
        return settings.secret_key
    if settings.env == "prod":
        raise RuntimeError("SECRET_KEY must be set when ENV=prod")
    log.warning("SECRET_KEY not set, using ephemeral key (sessions die on restart)")
    return _secrets.token_urlsafe(32)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import os

    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        _seed_singletons(db)
        _migrate_pdf_paths(db)
        # If LOAD_FIXTURE_PATH is set AND the DB has no projects yet, load
        # content from the JSON fixture. Idempotent on subsequent boots
        # because once projects exist the load is skipped.
        fixture_path = os.environ.get("LOAD_FIXTURE_PATH")
        if fixture_path:
            from pathlib import Path
            from backend.fixtures import load_content
            try:
                result = load_content(db, Path(fixture_path), only_if_empty=True)
                log.warning("LOAD_FIXTURE_PATH=%s result=%s", fixture_path, result)
            except Exception as e:
                log.error("LOAD_FIXTURE_PATH failed: %s", e)
        _warn_if_no_admin(db)
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    SessionMiddleware,
    secret_key=_resolve_secret_key(),
    session_cookie="portfolio_session",
    max_age=settings.session_max_age,
    same_site="lax",
    https_only=(settings.env == "prod"),
)

# Honor X-Forwarded-Proto/For from any upstream proxy (Railway terminates TLS
# at the edge). Added AFTER SessionMiddleware so it wraps it — runs first on
# inbound, patching scope["scheme"] to "https" before anything generates URLs.
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

app.mount("/static", StaticFiles(directory=ROOT / "frontend" / "static"), name="static")
# Some platforms (Railway/Fastly) intercept /static/* at the edge. Mount the
# same directory at /assets/* as a fallback so url_for('assets', path=...)
# bypasses any edge handling.
app.mount("/assets", StaticFiles(directory=ROOT / "frontend" / "static"), name="assets")
app.include_router(public_router)
app.include_router(blog_router)
app.include_router(admin_router)
