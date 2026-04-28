import logging
import secrets as _secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

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
    "pdf_path": "/static/resume.pdf",
}


def _seed_singletons(db: Session) -> None:
    if db.scalar(select(SiteMeta).where(SiteMeta.id == 1)) is None:
        db.add(SiteMeta(id=1, **DEFAULT_SITE))
    if db.scalar(select(ResumeMeta).where(ResumeMeta.id == 1)) is None:
        db.add(ResumeMeta(id=1, **DEFAULT_RESUME))
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


def _debug_static_paths() -> None:
    """One-shot startup diagnostic for missing static assets on Railway/etc."""
    static_dir = ROOT / "frontend" / "static"
    templates_dir = ROOT / "frontend" / "templates"
    log.warning("STATIC-DEBUG ROOT=%s exists=%s", ROOT, ROOT.is_dir())
    log.warning(
        "STATIC-DEBUG frontend/=%s frontend/static/=%s frontend/templates/=%s",
        (ROOT / "frontend").is_dir(),
        static_dir.is_dir(),
        templates_dir.is_dir(),
    )
    if static_dir.is_dir():
        names = sorted(p.name for p in static_dir.iterdir())
        log.warning("STATIC-DEBUG contents of frontend/static/: %s", names)
    log.warning(
        "STATIC-DEBUG styles.css exists=%s",
        (static_dir / "styles.css").is_file(),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _debug_static_paths()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        _seed_singletons(db)
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

# Temporary diagnostic endpoint — remove once the static-deploy issue is sorted.
@app.get("/_debug/static", include_in_schema=False)
def _debug_static_endpoint():
    import os

    static_dir = ROOT / "frontend" / "static"
    return {
        "root": str(ROOT),
        "cwd": os.getcwd(),
        "root_exists": ROOT.is_dir(),
        "static_dir_exists": static_dir.is_dir(),
        "static_dir_files": (
            sorted(os.listdir(static_dir)) if static_dir.is_dir() else None
        ),
        "styles_css_exists": (static_dir / "styles.css").is_file(),
        "__file__": __file__,
        "routes": [
            {
                "path": getattr(r, "path", None),
                "name": getattr(r, "name", None),
                "type": type(r).__name__,
            }
            for r in app.routes
        ],
    }


app.mount("/static", StaticFiles(directory=ROOT / "frontend" / "static"), name="static")
# Some platforms (Railway/Fastly) intercept /static/* at the edge. Mount the
# same directory at /assets/* as a fallback so url_for('assets', path=...)
# bypasses any edge handling.
app.mount("/assets", StaticFiles(directory=ROOT / "frontend" / "static"), name="assets")
app.include_router(public_router)
app.include_router(blog_router)
app.include_router(admin_router)
