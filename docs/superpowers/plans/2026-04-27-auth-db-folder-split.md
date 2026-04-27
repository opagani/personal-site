# Auth + SQLite + backend/frontend folder split — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evolve the public portfolio into an admin-editable site backed by SQLite, with Python under `backend/` and templates+static under `frontend/`, while keeping the public site visually identical on first boot.

**Architecture:** One FastAPI process. Server-rendered HTML via Jinja for both public and `/admin` pages — no JS framework. Auth via signed-cookie sessions + per-session CSRF token. SQLAlchemy 2.0 (sync) over SQLite. Bootstrap admin out-of-band via a CLI; never via a public route.

**Tech Stack:** FastAPI, Jinja2, SQLAlchemy 2.0, argon2-cffi (password hashing), Starlette `SessionMiddleware` + `itsdangerous`, pydantic-settings, python-multipart, pytest + httpx.

**Spec:** `docs/superpowers/specs/2026-04-27-auth-db-folder-split-design.md`

---

## File structure (target)

```
advanced-claude/
├── backend/
│   ├── __init__.py
│   ├── app.py                # FastAPI factory + middleware + router registration + seed
│   ├── settings.py           # pydantic-settings: env-var config
│   ├── db.py                 # engine, SessionLocal, Base, get_db dep
│   ├── models.py             # User, SiteMeta, Project, Link, ResumeMeta
│   ├── auth.py               # hash, verify, requires_admin, CSRF helpers
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── public.py         # GET /, /projects, /contact, /resume
│   │   └── admin.py          # all /admin/* routes
│   └── cli.py                # `python -m backend.cli create-admin`
├── frontend/
│   ├── templates/
│   │   ├── base.html
│   │   ├── public/{home,projects,contact,resume}.html
│   │   └── admin/{login,dashboard,site_form,project_list,project_form,link_list,link_form,resume_form}.html
│   └── static/styles.css
├── tests/
│   ├── conftest.py
│   ├── test_models.py
│   ├── test_public.py
│   ├── test_auth.py
│   ├── test_admin_meta.py
│   ├── test_admin_projects.py
│   ├── test_admin_links.py
│   └── test_cli.py
├── main.py                   # `from backend.app import app` + uvicorn launcher
├── .env.example
├── .gitignore                # add: site.db, .env
└── pyproject.toml
```

`content.py`, `templates/`, `static/` (root level) are deleted as part of Task 3.

---

## Task 1: Add dependencies and bootstrap test infra

**Files:**
- Modify: `pyproject.toml` (via `uv add`)
- Create: `tests/__init__.py`
- Create: `tests/conftest.py` (skeleton)

- [ ] **Step 1: Add production dependencies**

```bash
uv add 'sqlalchemy>=2.0' argon2-cffi itsdangerous pydantic-settings python-multipart
```

Expected: deps appear in `pyproject.toml` `[project.dependencies]`; `uv.lock` updated.

- [ ] **Step 2: Add dev dependencies**

```bash
uv add --dev pytest httpx
```

Expected: `[dependency-groups.dev]` (or `[tool.uv.dev-dependencies]` depending on uv version) lists `pytest` and `httpx`.

- [ ] **Step 3: Create empty test package**

```python
# tests/__init__.py
```

(Empty file. The directory needs to exist.)

- [ ] **Step 4: Create conftest skeleton**

```python
# tests/conftest.py
"""Shared pytest fixtures.

Real fixtures get added in later tasks (in-memory DB, TestClient, signed-in client).
"""
```

- [ ] **Step 5: Verify pytest can discover the (empty) test tree**

Run: `uv run pytest --collect-only`
Expected: `no tests ran` or `collected 0 items` — exit code 5 is OK at this stage. Just confirms the runner is wired.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock tests/__init__.py tests/conftest.py
git commit -m "chore: add SQLAlchemy/argon2/pytest deps + tests/ skeleton"
```

---

## Task 2: Scaffold `backend/` with settings, db, models

**Files:**
- Create: `backend/__init__.py`
- Create: `backend/settings.py`
- Create: `backend/db.py`
- Create: `backend/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing test for models**

```python
# tests/test_models.py
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.db import Base
from backend.models import User, SiteMeta, Project, Link, ResumeMeta


def _fresh_engine():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return engine


def test_create_all_creates_every_table():
    engine = _fresh_engine()
    expected = {"users", "site_meta", "projects", "links", "resume_meta"}
    assert expected.issubset(set(Base.metadata.tables.keys()))


def test_can_insert_and_query_each_model():
    engine = _fresh_engine()
    with Session(engine) as s:
        s.add(User(username="admin", password_hash="x"))
        s.add(SiteMeta(id=1, name="N", headline="H", bio="B"))
        s.add(Project(title="T", description="D", position=0))
        s.add(Link(label="GitHub", url="https://example.com", position=0))
        s.add(ResumeMeta(id=1, summary="S"))
        s.commit()

        assert s.query(User).count() == 1
        assert s.query(SiteMeta).one().name == "N"
        assert s.query(Project).one().title == "T"
        assert s.query(Link).one().label == "GitHub"
        assert s.query(ResumeMeta).one().summary == "S"


def test_user_username_is_unique():
    import sqlalchemy.exc
    engine = _fresh_engine()
    with Session(engine) as s:
        s.add(User(username="admin", password_hash="a"))
        s.commit()
        s.add(User(username="admin", password_hash="b"))
        try:
            s.commit()
            raised = False
        except sqlalchemy.exc.IntegrityError:
            raised = True
    assert raised


def test_timestamps_default_to_now_for_user_and_project():
    engine = _fresh_engine()
    with Session(engine) as s:
        u = User(username="u", password_hash="x")
        p = Project(title="t", description="d", position=0)
        s.add_all([u, p])
        s.commit()
        s.refresh(u); s.refresh(p)
        assert isinstance(u.created_at, datetime)
        assert isinstance(p.created_at, datetime)
        assert isinstance(p.updated_at, datetime)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend'`.

- [ ] **Step 3: Create `backend/__init__.py`**

```python
# backend/__init__.py
```

(Empty.)

- [ ] **Step 4: Create `backend/settings.py`**

```python
# backend/settings.py
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    env: Literal["dev", "prod"] = "dev"
    secret_key: str | None = None
    database_url: str = "sqlite:///./site.db"
    admin_username: str | None = None
    admin_password: str | None = None
    session_max_age: int = 60 * 60 * 24 * 7  # 7 days

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
```

- [ ] **Step 5: Create `backend/db.py`**

```python
# backend/db.py
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.settings import settings


class Base(DeclarativeBase):
    pass


# SQLite needs check_same_thread=False so sessions can be passed across threads
# (FastAPI runs sync deps in a threadpool).
_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, future=True, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 6: Create `backend/models.py`**

```python
# backend/models.py
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class SiteMeta(Base):
    __tablename__ = "site_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    bio: Mapped[str] = mapped_column(Text, nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    link: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Link(Base):
    __tablename__ = "links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(60), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ResumeMeta(Base):
    __tablename__ = "resume_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    pdf_path: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 7: Run tests, expect pass**

Run: `uv run pytest tests/test_models.py -v`
Expected: 4 passed.

- [ ] **Step 8: Commit**

```bash
git add backend/ tests/test_models.py
git commit -m "feat(backend): scaffold settings, db, and ORM models"
```

---

## Task 3: Move templates/static + DB-backed public routes + seed + retire `content.py`

**Files:**
- Create: `frontend/templates/base.html` (moved from `templates/base.html`, no content change)
- Create: `frontend/templates/public/home.html` (moved from `templates/home.html`)
- Create: `frontend/templates/public/projects.html` (moved from `templates/projects.html`)
- Create: `frontend/templates/public/contact.html` (moved from `templates/contact.html`)
- Create: `frontend/templates/public/resume.html` (moved from `templates/resume.html`)
- Create: `frontend/static/styles.css` (moved from `static/styles.css`)
- Create: `backend/routes/__init__.py`
- Create: `backend/routes/public.py`
- Create: `backend/app.py`
- Modify: `main.py` (rewrite)
- Delete: `content.py`, `templates/`, `static/`
- Modify: `.gitignore` (add `site.db`, `.env`)
- Create: `tests/test_public.py`

- [ ] **Step 1: Write failing test for DB-backed public site**

```python
# tests/test_public.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app import app
from backend.db import Base, get_db
from backend.models import Link, Project, ResumeMeta, SiteMeta


@pytest.fixture
def client():
    engine = create_engine("sqlite:///:memory:", future=True, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    with TestSession() as s:
        s.add(SiteMeta(id=1, name="Ada Lovelace", headline="Mathematician", bio="Notes on the Analytical Engine."))
        s.add(ResumeMeta(id=1, summary="Long-form summary.", pdf_path="/static/resume.pdf"))
        s.add(Project(title="Note G", description="The first algorithm.", link="https://example.com", position=0))
        s.add(Link(label="GitHub", url="https://github.com/ada", position=0))
        s.commit()

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_home_renders_site_meta(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Ada Lovelace" in r.text
    assert "Mathematician" in r.text
    assert 'aria-current="page"' in r.text


def test_projects_renders_db_rows(client):
    r = client.get("/projects")
    assert r.status_code == 200
    assert "Note G" in r.text
    assert "The first algorithm." in r.text


def test_contact_renders_links(client):
    r = client.get("/contact")
    assert r.status_code == 200
    assert "GitHub" in r.text
    assert "https://github.com/ada" in r.text


def test_resume_renders_summary_and_handles_missing_pdf(client):
    r = client.get("/resume")
    assert r.status_code == 200
    assert "Long-form summary." in r.text
    # In test env there's no PDF on disk, so the missing-PDF branch should render
    assert "PDF not yet uploaded" in r.text


def test_static_styles_served(client):
    r = client.get("/static/styles.css")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/css")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_public.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.app'`.

- [ ] **Step 3: Move template files into `frontend/templates/`**

```bash
mkdir -p frontend/templates/public frontend/static
git mv templates/base.html frontend/templates/base.html
git mv templates/home.html frontend/templates/public/home.html
git mv templates/projects.html frontend/templates/public/projects.html
git mv templates/contact.html frontend/templates/public/contact.html
git mv templates/resume.html frontend/templates/public/resume.html
git mv static/styles.css frontend/static/styles.css
rmdir templates static
```

- [ ] **Step 4: Update `frontend/templates/base.html` static URL helper**

The Jinja `url_for('static', path='styles.css')` call still works because the mount name stays `'static'`. **No change needed** to base.html. Verify by reading it.

- [ ] **Step 5: Create `backend/routes/__init__.py`**

```python
# backend/routes/__init__.py
```

(Empty.)

- [ ] **Step 6: Create `backend/routes/public.py`**

```python
# backend/routes/public.py
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


def _site(db: Session) -> SiteMeta:
    return db.scalar(select(SiteMeta).where(SiteMeta.id == 1))


@router.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request, "public/home.html",
        {"site": _site(db), "current_page": "home"},
    )


@router.get("/projects")
def projects(request: Request, db: Session = Depends(get_db)):
    rows = db.scalars(select(Project).order_by(Project.position, Project.id)).all()
    return templates.TemplateResponse(
        request, "public/projects.html",
        {"site": _site(db), "projects": rows, "current_page": "projects"},
    )


@router.get("/contact")
def contact(request: Request, db: Session = Depends(get_db)):
    rows = db.scalars(select(Link).order_by(Link.position, Link.id)).all()
    return templates.TemplateResponse(
        request, "public/contact.html",
        {"site": _site(db), "links": rows, "current_page": "contact"},
    )


@router.get("/resume")
def resume(request: Request, db: Session = Depends(get_db)):
    site = _site(db)
    rmeta = db.scalar(select(ResumeMeta).where(ResumeMeta.id == 1))
    pdf_path_on_disk = ROOT / "frontend" / "static" / "resume.pdf"
    pdf_available = bool(rmeta and rmeta.pdf_path) and pdf_path_on_disk.is_file()
    return templates.TemplateResponse(
        request, "public/resume.html",
        {
            "site": site,
            "resume": rmeta,
            "resume_pdf_available": pdf_available,
            "current_page": "resume",
        },
    )
```

- [ ] **Step 7: Create `backend/app.py` with seed-on-startup**

```python
# backend/app.py
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db import Base, SessionLocal, engine
from backend.models import ResumeMeta, SiteMeta, User
from backend.routes.public import router as public_router

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
        log.warning(
            "No admin user. Run: uv run python -m backend.cli create-admin"
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        _seed_singletons(db)
        _warn_if_no_admin(db)
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "frontend" / "static"), name="static")
app.include_router(public_router)
```

- [ ] **Step 8: Rewrite `main.py` to launch `backend.app:app`**

```python
# main.py
import uvicorn

from backend.app import app  # noqa: F401  (uvicorn imports by string below)

if __name__ == "__main__":
    uvicorn.run("backend.app:app", host="127.0.0.1", port=8000, reload=True)
```

- [ ] **Step 9: Delete legacy `content.py`**

```bash
git rm content.py
```

- [ ] **Step 10: Update `.gitignore`**

Add these two lines to `.gitignore`:

```
# Database + secrets
site.db
.env
```

(Append below the `.superpowers/` block.)

- [ ] **Step 11: Run all tests**

Run: `uv run pytest -v`
Expected: tests in `test_models.py` (4) + `test_public.py` (5) all pass = 9 passed.

- [ ] **Step 12: Commit**

```bash
git add -A
git commit -m "refactor: split backend/frontend, switch public routes to SQLite, seed defaults"
```

---

## Task 4: Auth helpers (hashing + CSRF + dependency)

**Files:**
- Create: `backend/auth.py`
- Create: `tests/test_auth.py`

- [ ] **Step 1: Write failing test for hashing + CSRF check**

```python
# tests/test_auth.py
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.auth import (
    CSRF_FIELD,
    SESSION_KEY_CSRF,
    SESSION_KEY_USER,
    generate_csrf_token,
    hash_password,
    verify_password,
    verify_csrf,
)


def _request_with_session(session: dict) -> Request:
    """Build a minimal Starlette Request with a writable session dict."""
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/admin/site",
        "headers": [],
        "session": session,
    }
    return Request(scope)


def test_hash_and_verify_round_trip():
    h = hash_password("hunter2")
    assert h != "hunter2"
    assert verify_password(h, "hunter2") is True
    assert verify_password(h, "wrong") is False


def test_generate_csrf_token_is_url_safe_and_random():
    a = generate_csrf_token()
    b = generate_csrf_token()
    assert a != b
    assert len(a) >= 32
    # url-safe base64 chars only
    import re
    assert re.fullmatch(r"[A-Za-z0-9_-]+", a)


def test_verify_csrf_passes_on_match():
    session = {SESSION_KEY_CSRF: "abc"}
    req = _request_with_session(session)
    verify_csrf(req, submitted="abc")  # no exception


def test_verify_csrf_raises_on_mismatch():
    session = {SESSION_KEY_CSRF: "abc"}
    req = _request_with_session(session)
    with pytest.raises(HTTPException) as exc:
        verify_csrf(req, submitted="zzz")
    assert exc.value.status_code == 403


def test_verify_csrf_raises_when_session_missing_token():
    req = _request_with_session({})
    with pytest.raises(HTTPException):
        verify_csrf(req, submitted="abc")


def test_session_key_constants_are_strings():
    assert isinstance(SESSION_KEY_USER, str)
    assert isinstance(SESSION_KEY_CSRF, str)
    assert CSRF_FIELD == "csrf"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.auth'`.

- [ ] **Step 3: Implement `backend/auth.py`**

```python
# backend/auth.py
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Form, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import User

# Session keys
SESSION_KEY_USER = "user_id"
SESSION_KEY_CSRF = "csrf"

# HTML form field name for CSRF token
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
    """Make sure the session carries a CSRF token; return it."""
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
    """FastAPI dep: pulls the CSRF field out of the submitted form."""
    return csrf
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_auth.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/auth.py tests/test_auth.py
git commit -m "feat(auth): password hashing + CSRF helpers + session keys"
```

---

## Task 5: Login/logout routes + SessionMiddleware

**Files:**
- Modify: `backend/app.py` (add SessionMiddleware + admin router)
- Create: `backend/routes/admin.py`
- Create: `frontend/templates/admin/base.html`
- Create: `frontend/templates/admin/login.html`
- Create: `frontend/templates/admin/dashboard.html`
- Modify: `tests/conftest.py` (add `signed_in_client` fixture)
- Modify: `tests/test_auth.py` (add login flow tests)

- [ ] **Step 1: Add wider conftest fixtures**

Replace the contents of `tests/conftest.py` with:

```python
# tests/conftest.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app import app
from backend.auth import hash_password
from backend.db import Base, get_db
from backend.models import Link, Project, ResumeMeta, SiteMeta, User


@pytest.fixture
def db_factory():
    """Yield a sessionmaker bound to a fresh in-memory SQLite DB.

    Seeds the singletons + an admin user (`admin` / `secret`).
    """
    engine = create_engine(
        "sqlite:///:memory:", future=True, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    with Session() as s:
        s.add(SiteMeta(id=1, name="Ada Lovelace", headline="Mathematician", bio="Notes."))
        s.add(ResumeMeta(id=1, summary="Summary text.", pdf_path="/static/resume.pdf"))
        s.add(User(username="admin", password_hash=hash_password("secret")))
        s.commit()

    return Session


@pytest.fixture
def client(db_factory):
    Session = db_factory

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _extract_csrf(html: str) -> str:
    import re
    m = re.search(r'name="csrf"\s+value="([^"]+)"', html)
    assert m, "CSRF token not found in form HTML"
    return m.group(1)


@pytest.fixture
def signed_in_client(client):
    """A TestClient already logged in as `admin` / `secret`."""
    r = client.get("/admin/login")
    csrf = _extract_csrf(r.text)
    r = client.post(
        "/admin/login",
        data={"username": "admin", "password": "secret", "csrf": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    return client


@pytest.fixture
def get_csrf(signed_in_client):
    """Returns a callable that fetches a fresh CSRF token from a given GET path."""
    def _get(path: str) -> str:
        r = signed_in_client.get(path)
        assert r.status_code == 200, f"GET {path} returned {r.status_code}"
        return _extract_csrf(r.text)
    return _get


@pytest.fixture
def db_factory_with_seed(db_factory):
    """Convenience: returns the sessionmaker so tests can seed extra rows.

    Used by admin CRUD tests that pre-populate projects / links.
    """
    return db_factory
```

- [ ] **Step 2: Write failing tests for login/logout**

Append to `tests/test_auth.py`:

```python
def test_admin_unauthenticated_redirects_to_login(client):
    r = client.get("/admin", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].endswith("/admin/login")


def test_admin_login_get_serves_form_with_csrf(client):
    r = client.get("/admin/login")
    assert r.status_code == 200
    assert 'name="csrf"' in r.text
    assert 'name="username"' in r.text
    assert 'name="password"' in r.text


def test_admin_login_wrong_password_renders_error(client):
    r = client.get("/admin/login")
    csrf = _extract_csrf_helper(r.text)
    r = client.post(
        "/admin/login",
        data={"username": "admin", "password": "wrong", "csrf": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 200
    assert "Invalid" in r.text or "incorrect" in r.text.lower()


def test_admin_login_correct_redirects_to_dashboard(client):
    r = client.get("/admin/login")
    csrf = _extract_csrf_helper(r.text)
    r = client.post(
        "/admin/login",
        data={"username": "admin", "password": "secret", "csrf": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"].endswith("/admin")


def test_admin_dashboard_when_signed_in(signed_in_client):
    r = signed_in_client.get("/admin")
    assert r.status_code == 200
    assert "Dashboard" in r.text or "admin" in r.text.lower()


def test_admin_logout_clears_session(signed_in_client):
    r = signed_in_client.get("/admin")
    csrf = _extract_csrf_helper(r.text)
    r = signed_in_client.post(
        "/admin/logout",
        data={"csrf": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303
    # After logout, /admin should bounce back to login
    r = signed_in_client.get("/admin", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].endswith("/admin/login")


def test_login_post_without_csrf_is_rejected(client):
    r = client.post(
        "/admin/login",
        data={"username": "admin", "password": "secret"},
        follow_redirects=False,
    )
    # No CSRF field at all -> 403 (Form(...) for csrf is required)
    assert r.status_code in (403, 422)


def _extract_csrf_helper(html: str) -> str:
    import re
    m = re.search(r'name="csrf"\s+value="([^"]+)"', html)
    assert m
    return m.group(1)
```

- [ ] **Step 3: Run new tests to verify they fail**

Run: `uv run pytest tests/test_auth.py -v`
Expected: the original 6 still pass; the new ones fail with 404 / missing route errors.

- [ ] **Step 4: Wire SessionMiddleware + admin router in `backend/app.py`**

Modify `backend/app.py`:

```python
# backend/app.py
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


@asynccontextmanager
async def lifespan(app: FastAPI):
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

app.mount("/static", StaticFiles(directory=ROOT / "frontend" / "static"), name="static")
app.include_router(public_router)
app.include_router(admin_router)
```

- [ ] **Step 5: Create `frontend/templates/admin/base.html`**

```html
<!-- frontend/templates/admin/base.html -->
{% extends "base.html" %}

{% block content %}
<div class="admin-shell">
  <p class="admin-banner">
    Admin
    {% if user %}
      · signed in as <strong>{{ user.username }}</strong>
      <form method="post" action="/admin/logout" style="display:inline">
        <input type="hidden" name="csrf" value="{{ csrf_token }}">
        <button class="link-button" type="submit">log out</button>
      </form>
    {% endif %}
  </p>

  {% block admin %}{% endblock %}
</div>
{% endblock %}
```

- [ ] **Step 6: Create `frontend/templates/admin/login.html`**

```html
<!-- frontend/templates/admin/login.html -->
{% extends "base.html" %}
{% block title %}Admin login · {{ site.name }}{% endblock %}

{% block content %}
<h1>Admin login</h1>

{% if error %}
  <p class="error">{{ error }}</p>
{% endif %}

{% if not configured %}
  <p class="muted">
    No admin user exists yet. Run
    <code>uv run python -m backend.cli create-admin</code> to create one.
  </p>
{% else %}
  <form method="post" action="/admin/login" class="auth-form">
    <input type="hidden" name="csrf" value="{{ csrf_token }}">
    <label>Username
      <input name="username" required autofocus>
    </label>
    <label>Password
      <input name="password" type="password" required>
    </label>
    <button type="submit">Sign in</button>
  </form>
{% endif %}
{% endblock %}
```

- [ ] **Step 7: Create `frontend/templates/admin/dashboard.html`**

```html
<!-- frontend/templates/admin/dashboard.html -->
{% extends "admin/base.html" %}
{% block title %}Dashboard · {{ site.name }}{% endblock %}

{% block admin %}
<h1>Dashboard</h1>
<ul class="admin-nav">
  <li><a href="/admin/site">Edit site (name, headline, bio)</a></li>
  <li><a href="/admin/projects">Manage projects</a></li>
  <li><a href="/admin/links">Manage contact links</a></li>
  <li><a href="/admin/resume">Edit resume</a></li>
</ul>
{% endblock %}
```

- [ ] **Step 8: Create `backend/routes/admin.py` with login/logout/dashboard**

```python
# backend/routes/admin.py
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
    hash_password,  # noqa: F401  (re-exported for cli convenience? remove if unused)
    rotate_csrf_token,
    verify_csrf,
    verify_password,
)
from backend.db import get_db
from backend.models import User

ROOT = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=ROOT / "frontend" / "templates")

router = APIRouter(prefix="/admin")


def _site_meta(db: Session):
    from backend.models import SiteMeta
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
        request, "admin/login.html",
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
        # Re-render with error; keep CSRF token (don't rotate on failed login)
        csrf_token = ensure_csrf_token(request)
        has_admin = db.scalar(select(User).limit(1)) is not None
        return templates.TemplateResponse(
            request, "admin/login.html",
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
        request, "admin/dashboard.html",
        {
            "site": _site_meta(db),
            "user": user,
            "csrf_token": ensure_csrf_token(request),
            "current_page": None,
        },
    )
```

- [ ] **Step 9: Run all tests**

Run: `uv run pytest -v`
Expected: all `test_models.py`, `test_public.py`, `test_auth.py` pass.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "feat(auth): SessionMiddleware + login/logout/dashboard"
```

---

## Task 6: Admin editors for `site_meta` and `resume_meta` (singletons)

**Files:**
- Modify: `backend/routes/admin.py` (add four routes)
- Create: `frontend/templates/admin/site_form.html`
- Create: `frontend/templates/admin/resume_form.html`
- Create: `tests/test_admin_meta.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_admin_meta.py
from sqlalchemy import select

from backend.models import SiteMeta, ResumeMeta


def _factory_session(db_factory):
    return db_factory()


def test_get_admin_site_renders_prefilled_form(signed_in_client):
    r = signed_in_client.get("/admin/site")
    assert r.status_code == 200
    assert 'value="Ada Lovelace"' in r.text
    assert 'name="csrf"' in r.text


def test_post_admin_site_updates_db(signed_in_client, get_csrf, db_factory_with_seed):
    csrf = get_csrf("/admin/site")
    r = signed_in_client.post(
        "/admin/site",
        data={
            "csrf": csrf,
            "name": "Grace Hopper",
            "headline": "Rear Admiral, USN",
            "bio": "Compiler pioneer.",
            "avatar_url": "",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"].endswith("/admin/site")

    with db_factory_with_seed() as db:
        sm = db.scalar(select(SiteMeta).where(SiteMeta.id == 1))
        assert sm.name == "Grace Hopper"
        assert sm.headline == "Rear Admiral, USN"
        assert sm.avatar_url is None  # empty string → None


def test_post_admin_site_without_csrf_is_403(signed_in_client):
    r = signed_in_client.post(
        "/admin/site",
        data={"name": "X", "headline": "Y", "bio": "Z", "avatar_url": ""},
        follow_redirects=False,
    )
    assert r.status_code in (403, 422)


def test_post_admin_resume_updates_db(signed_in_client, get_csrf, db_factory_with_seed):
    csrf = get_csrf("/admin/resume")
    r = signed_in_client.post(
        "/admin/resume",
        data={
            "csrf": csrf,
            "summary": "New summary.",
            "pdf_path": "/static/resume.pdf",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    with db_factory_with_seed() as db:
        rm = db.scalar(select(ResumeMeta).where(ResumeMeta.id == 1))
        assert rm.summary == "New summary."
```

- [ ] **Step 2: Run tests, expect fail (404)**

Run: `uv run pytest tests/test_admin_meta.py -v`
Expected: FAIL with 404.

- [ ] **Step 3: Create `frontend/templates/admin/site_form.html`**

```html
<!-- frontend/templates/admin/site_form.html -->
{% extends "admin/base.html" %}
{% block title %}Edit site · {{ site.name }}{% endblock %}

{% block admin %}
<p><a href="/admin">← back to dashboard</a></p>
<h1>Edit site</h1>

<form method="post" action="/admin/site" class="admin-form">
  <input type="hidden" name="csrf" value="{{ csrf_token }}">
  <label>Name
    <input name="name" value="{{ site.name }}" required>
  </label>
  <label>Headline
    <input name="headline" value="{{ site.headline }}" required>
  </label>
  <label>Bio
    <textarea name="bio" rows="6" required>{{ site.bio }}</textarea>
  </label>
  <label>Avatar URL (optional)
    <input name="avatar_url" value="{{ site.avatar_url or '' }}">
  </label>
  <button type="submit">Save</button>
</form>
{% endblock %}
```

- [ ] **Step 4: Create `frontend/templates/admin/resume_form.html`**

```html
<!-- frontend/templates/admin/resume_form.html -->
{% extends "admin/base.html" %}
{% block title %}Edit resume · {{ site.name }}{% endblock %}

{% block admin %}
<p><a href="/admin">← back to dashboard</a></p>
<h1>Edit resume</h1>

<form method="post" action="/admin/resume" class="admin-form">
  <input type="hidden" name="csrf" value="{{ csrf_token }}">
  <label>Summary
    <textarea name="summary" rows="6" required>{{ resume.summary }}</textarea>
  </label>
  <label>PDF path (e.g. <code>/static/resume.pdf</code>)
    <input name="pdf_path" value="{{ resume.pdf_path or '' }}">
  </label>
  <button type="submit">Save</button>
</form>

<p class="muted">Drop the PDF file at <code>frontend/static/resume.pdf</code> on the server. The download link only appears if the file exists.</p>
{% endblock %}
```

- [ ] **Step 5: Append singleton-editor routes to `backend/routes/admin.py`**

Append to `backend/routes/admin.py`:

```python
from backend.models import ResumeMeta, SiteMeta  # already partially imported


@router.get("/site")
def site_form(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(requires_admin),
):
    return templates.TemplateResponse(
        request, "admin/site_form.html",
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


@router.get("/resume")
def resume_form(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(requires_admin),
):
    rm = db.scalar(select(ResumeMeta).where(ResumeMeta.id == 1))
    return templates.TemplateResponse(
        request, "admin/resume_form.html",
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
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_admin_meta.py -v`
Expected: 4 passed.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(admin): edit forms for site_meta and resume_meta singletons"
```

---

## Task 7: Admin projects CRUD

**Files:**
- Modify: `backend/routes/admin.py` (add six routes)
- Create: `frontend/templates/admin/project_list.html`
- Create: `frontend/templates/admin/project_form.html`
- Create: `tests/test_admin_projects.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_admin_projects.py
from sqlalchemy import select

from backend.models import Project


def test_admin_projects_list_when_empty(signed_in_client):
    r = signed_in_client.get("/admin/projects")
    assert r.status_code == 200
    assert "No projects yet" in r.text or "Add" in r.text


def test_create_project(signed_in_client, get_csrf, db_factory_with_seed):
    csrf = get_csrf("/admin/projects/new")
    r = signed_in_client.post(
        "/admin/projects/new",
        data={
            "csrf": csrf,
            "title": "Note G",
            "description": "First algorithm.",
            "link": "https://example.com",
            "position": "0",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"].endswith("/admin/projects")
    with db_factory_with_seed() as db:
        p = db.scalar(select(Project).where(Project.title == "Note G"))
        assert p is not None
        assert p.description == "First algorithm."


def test_edit_project(signed_in_client, get_csrf, db_factory_with_seed):
    # First create
    csrf = get_csrf("/admin/projects/new")
    signed_in_client.post(
        "/admin/projects/new",
        data={"csrf": csrf, "title": "Initial", "description": "d", "link": "", "position": "0"},
        follow_redirects=False,
    )
    with db_factory_with_seed() as db:
        pid = db.scalar(select(Project.id).where(Project.title == "Initial"))

    # Then edit
    csrf = get_csrf(f"/admin/projects/{pid}")
    r = signed_in_client.post(
        f"/admin/projects/{pid}",
        data={"csrf": csrf, "title": "Renamed", "description": "d2", "link": "", "position": "5"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    with db_factory_with_seed() as db:
        p = db.scalar(select(Project).where(Project.id == pid))
        assert p.title == "Renamed"
        assert p.description == "d2"
        assert p.position == 5


def test_delete_project(signed_in_client, get_csrf, db_factory_with_seed):
    csrf = get_csrf("/admin/projects/new")
    signed_in_client.post(
        "/admin/projects/new",
        data={"csrf": csrf, "title": "Doomed", "description": "d", "link": "", "position": "0"},
        follow_redirects=False,
    )
    with db_factory_with_seed() as db:
        pid = db.scalar(select(Project.id).where(Project.title == "Doomed"))

    csrf = get_csrf("/admin/projects")
    r = signed_in_client.post(
        f"/admin/projects/{pid}/delete",
        data={"csrf": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303
    with db_factory_with_seed() as db:
        assert db.scalar(select(Project).where(Project.id == pid)) is None


def test_public_projects_reflects_db_changes(signed_in_client, client, get_csrf):
    csrf = get_csrf("/admin/projects/new")
    signed_in_client.post(
        "/admin/projects/new",
        data={"csrf": csrf, "title": "Visible", "description": "Public copy.", "link": "", "position": "0"},
        follow_redirects=False,
    )
    r = client.get("/projects")
    assert "Visible" in r.text
    assert "Public copy." in r.text


def test_get_unknown_project_returns_404(signed_in_client):
    r = signed_in_client.get("/admin/projects/9999")
    assert r.status_code == 404
```

- [ ] **Step 2: Run tests, expect fail**

Run: `uv run pytest tests/test_admin_projects.py -v`
Expected: FAIL.

- [ ] **Step 3: Create `frontend/templates/admin/project_list.html`**

```html
<!-- frontend/templates/admin/project_list.html -->
{% extends "admin/base.html" %}
{% block title %}Projects · {{ site.name }}{% endblock %}

{% block admin %}
<p><a href="/admin">← back to dashboard</a></p>
<h1>Projects</h1>
<p><a class="button" href="/admin/projects/new">+ New project</a></p>

{% if projects %}
  <ul class="admin-list">
    {% for p in projects %}
      <li>
        <strong><a href="/admin/projects/{{ p.id }}">{{ p.title }}</a></strong>
        <span class="muted">(position {{ p.position }})</span>
        <form method="post" action="/admin/projects/{{ p.id }}/delete" style="display:inline">
          <input type="hidden" name="csrf" value="{{ csrf_token }}">
          <button class="link-button" type="submit"
                  onclick="return confirm('Delete &quot;{{ p.title }}&quot;?');">delete</button>
        </form>
      </li>
    {% endfor %}
  </ul>
{% else %}
  <p class="muted">No projects yet.</p>
{% endif %}
{% endblock %}
```

- [ ] **Step 4: Create `frontend/templates/admin/project_form.html`**

```html
<!-- frontend/templates/admin/project_form.html -->
{% extends "admin/base.html" %}
{% block title %}{{ "New" if is_new else "Edit" }} project · {{ site.name }}{% endblock %}

{% block admin %}
<p><a href="/admin/projects">← back to projects</a></p>
<h1>{{ "New project" if is_new else "Edit project" }}</h1>

<form method="post" action="{{ '/admin/projects/new' if is_new else '/admin/projects/' ~ project.id }}" class="admin-form">
  <input type="hidden" name="csrf" value="{{ csrf_token }}">
  <label>Title
    <input name="title" value="{{ project.title or '' }}" required>
  </label>
  <label>Description
    <textarea name="description" rows="5" required>{{ project.description or '' }}</textarea>
  </label>
  <label>Link (optional)
    <input name="link" value="{{ project.link or '' }}">
  </label>
  <label>Position (lower = earlier)
    <input name="position" type="number" value="{{ project.position if project.position is not none else 0 }}">
  </label>
  <button type="submit">{{ "Create" if is_new else "Save" }}</button>
</form>
{% endblock %}
```

- [ ] **Step 5: Append project routes to `backend/routes/admin.py`**

Append:

```python
from types import SimpleNamespace

from backend.models import Project


@router.get("/projects")
def projects_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(requires_admin),
):
    rows = db.scalars(select(Project).order_by(Project.position, Project.id)).all()
    return templates.TemplateResponse(
        request, "admin/project_list.html",
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
        request, "admin/project_form.html",
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
        request, "admin/project_form.html",
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
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_admin_projects.py -v`
Expected: 6 passed.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(admin): projects CRUD"
```

---

## Task 8: Admin links CRUD

**Files:**
- Modify: `backend/routes/admin.py` (add six routes — same shape as projects)
- Create: `frontend/templates/admin/link_list.html`
- Create: `frontend/templates/admin/link_form.html`
- Create: `tests/test_admin_links.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_admin_links.py
from sqlalchemy import select

from backend.models import Link


def test_create_edit_delete_link(signed_in_client, get_csrf, db_factory_with_seed):
    # Create
    csrf = get_csrf("/admin/links/new")
    r = signed_in_client.post(
        "/admin/links/new",
        data={"csrf": csrf, "label": "GitHub", "url": "https://github.com/x", "position": "0"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    with db_factory_with_seed() as db:
        link = db.scalar(select(Link).where(Link.label == "GitHub"))
        assert link is not None
        lid = link.id

    # Edit
    csrf = get_csrf(f"/admin/links/{lid}")
    r = signed_in_client.post(
        f"/admin/links/{lid}",
        data={"csrf": csrf, "label": "Github (lowercase)", "url": "https://github.com/x", "position": "1"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    with db_factory_with_seed() as db:
        link = db.scalar(select(Link).where(Link.id == lid))
        assert link.label == "Github (lowercase)"
        assert link.position == 1

    # Delete
    csrf = get_csrf("/admin/links")
    r = signed_in_client.post(
        f"/admin/links/{lid}/delete",
        data={"csrf": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303
    with db_factory_with_seed() as db:
        assert db.scalar(select(Link).where(Link.id == lid)) is None


def test_public_contact_reflects_link_changes(signed_in_client, client, get_csrf):
    csrf = get_csrf("/admin/links/new")
    signed_in_client.post(
        "/admin/links/new",
        data={"csrf": csrf, "label": "Email", "url": "mailto:x@example.com", "position": "0"},
        follow_redirects=False,
    )
    r = client.get("/contact")
    assert "Email" in r.text
    assert "mailto:x@example.com" in r.text
```

- [ ] **Step 2: Run tests, expect fail**

Run: `uv run pytest tests/test_admin_links.py -v`
Expected: FAIL with 404.

- [ ] **Step 3: Create `frontend/templates/admin/link_list.html`**

```html
<!-- frontend/templates/admin/link_list.html -->
{% extends "admin/base.html" %}
{% block title %}Contact links · {{ site.name }}{% endblock %}

{% block admin %}
<p><a href="/admin">← back to dashboard</a></p>
<h1>Contact links</h1>
<p><a class="button" href="/admin/links/new">+ New link</a></p>

{% if links %}
  <ul class="admin-list">
    {% for l in links %}
      <li>
        <strong><a href="/admin/links/{{ l.id }}">{{ l.label }}</a></strong>
        <span class="muted">→ {{ l.url }} (position {{ l.position }})</span>
        <form method="post" action="/admin/links/{{ l.id }}/delete" style="display:inline">
          <input type="hidden" name="csrf" value="{{ csrf_token }}">
          <button class="link-button" type="submit"
                  onclick="return confirm('Delete &quot;{{ l.label }}&quot;?');">delete</button>
        </form>
      </li>
    {% endfor %}
  </ul>
{% else %}
  <p class="muted">No links yet.</p>
{% endif %}
{% endblock %}
```

- [ ] **Step 4: Create `frontend/templates/admin/link_form.html`**

```html
<!-- frontend/templates/admin/link_form.html -->
{% extends "admin/base.html" %}
{% block title %}{{ "New" if is_new else "Edit" }} link · {{ site.name }}{% endblock %}

{% block admin %}
<p><a href="/admin/links">← back to links</a></p>
<h1>{{ "New link" if is_new else "Edit link" }}</h1>

<form method="post" action="{{ '/admin/links/new' if is_new else '/admin/links/' ~ link.id }}" class="admin-form">
  <input type="hidden" name="csrf" value="{{ csrf_token }}">
  <label>Label
    <input name="label" value="{{ link.label or '' }}" required>
  </label>
  <label>URL
    <input name="url" value="{{ link.url or '' }}" required>
  </label>
  <label>Position (lower = earlier)
    <input name="position" type="number" value="{{ link.position if link.position is not none else 0 }}">
  </label>
  <button type="submit">{{ "Create" if is_new else "Save" }}</button>
</form>
{% endblock %}
```

- [ ] **Step 5: Append link routes to `backend/routes/admin.py`**

Append (re-using the `SimpleNamespace` import from Task 7):

```python
from backend.models import Link


@router.get("/links")
def links_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(requires_admin),
):
    rows = db.scalars(select(Link).order_by(Link.position, Link.id)).all()
    return templates.TemplateResponse(
        request, "admin/link_list.html",
        {
            "site": _site_meta(db),
            "links": rows,
            "user": user,
            "csrf_token": ensure_csrf_token(request),
            "current_page": None,
        },
    )


@router.get("/links/new")
def link_new_form(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(requires_admin),
):
    blank = SimpleNamespace(id=None, label="", url="", position=0)
    return templates.TemplateResponse(
        request, "admin/link_form.html",
        {
            "site": _site_meta(db),
            "link": blank,
            "is_new": True,
            "user": user,
            "csrf_token": ensure_csrf_token(request),
            "current_page": None,
        },
    )


@router.post("/links/new")
def link_create(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(requires_admin_post),
    label: str = Form(...),
    url: str = Form(...),
    position: int = Form(0),
):
    db.add(Link(label=label, url=url, position=position))
    db.commit()
    return RedirectResponse(url="/admin/links", status_code=303)


@router.get("/links/{link_id}")
def link_edit_form(
    link_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(requires_admin),
):
    link = db.scalar(select(Link).where(Link.id == link_id))
    if link is None:
        raise HTTPException(status_code=404, detail="Link not found")
    return templates.TemplateResponse(
        request, "admin/link_form.html",
        {
            "site": _site_meta(db),
            "link": link,
            "is_new": False,
            "user": user,
            "csrf_token": ensure_csrf_token(request),
            "current_page": None,
        },
    )


@router.post("/links/{link_id}")
def link_update(
    link_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(requires_admin_post),
    label: str = Form(...),
    url: str = Form(...),
    position: int = Form(0),
):
    link = db.scalar(select(Link).where(Link.id == link_id))
    if link is None:
        raise HTTPException(status_code=404, detail="Link not found")
    link.label = label
    link.url = url
    link.position = position
    db.commit()
    return RedirectResponse(url="/admin/links", status_code=303)


@router.post("/links/{link_id}/delete")
def link_delete(
    link_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(requires_admin_post),
):
    link = db.scalar(select(Link).where(Link.id == link_id))
    if link is None:
        raise HTTPException(status_code=404, detail="Link not found")
    db.delete(link)
    db.commit()
    return RedirectResponse(url="/admin/links", status_code=303)
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_admin_links.py -v`
Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(admin): links CRUD"
```

---

## Task 9: CLI `create-admin`

**Files:**
- Create: `backend/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_cli.py
from sqlalchemy import select

from backend.cli import create_admin
from backend.models import User


def test_create_admin_inserts_a_hashed_user(db_factory):
    Session = db_factory
    # The fixture seeds a user; remove it for this test
    with Session() as s:
        for u in s.scalars(select(User)).all():
            s.delete(u)
        s.commit()

    create_admin("ada", "lovelace", session_factory=Session)

    with Session() as s:
        u = s.scalar(select(User).where(User.username == "ada"))
        assert u is not None
        assert u.password_hash != "lovelace"  # hashed
        # Hashed by argon2 — round-trip
        from backend.auth import verify_password
        assert verify_password(u.password_hash, "lovelace")


def test_create_admin_refuses_second_user(db_factory):
    Session = db_factory  # already seeds an `admin` user
    import pytest
    with pytest.raises(SystemExit):
        create_admin("second", "x", session_factory=Session)
```

- [ ] **Step 2: Run test, expect ImportError**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.cli'`.

- [ ] **Step 3: Create `backend/cli.py`**

```python
# backend/cli.py
"""CLI entry point.

Usage:
    uv run python -m backend.cli create-admin
"""

from __future__ import annotations

import argparse
import getpass
import sys
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session as _Session

from backend.auth import hash_password
from backend.db import Base, SessionLocal, engine
from backend.models import User
from backend.settings import settings


def create_admin(
    username: str,
    password: str,
    session_factory: Callable[[], _Session] = SessionLocal,
) -> None:
    """Insert a single admin user. Aborts if any user already exists."""
    with session_factory() as db:
        existing = db.scalar(select(User).limit(1))
        if existing is not None:
            print(
                f"An admin user already exists: {existing.username}. "
                "This is a single-admin system.",
                file=sys.stderr,
            )
            raise SystemExit(1)
        db.add(User(username=username, password_hash=hash_password(password)))
        db.commit()
    print(f"Created admin user '{username}'.")


def _cmd_create_admin(args: argparse.Namespace) -> None:
    Base.metadata.create_all(engine)

    username = args.username or settings.admin_username or input("Username: ").strip()
    if not username:
        print("Username required.", file=sys.stderr)
        raise SystemExit(2)

    password = args.password or settings.admin_password
    if not password:
        password = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm:  ")
        if password != confirm:
            print("Passwords don't match.", file=sys.stderr)
            raise SystemExit(2)

    create_admin(username, password)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="backend.cli")
    sub = p.add_subparsers(dest="cmd", required=True)

    ca = sub.add_parser("create-admin", help="Create the single admin user")
    ca.add_argument("--username", help="(falls back to ADMIN_USERNAME or interactive prompt)")
    ca.add_argument("--password", help="(falls back to ADMIN_PASSWORD or interactive prompt)")
    ca.set_defaults(func=_cmd_create_admin)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_cli.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/cli.py tests/test_cli.py
git commit -m "feat(cli): create-admin command"
```

---

## Task 10: Styles for the admin shell, .env.example, README, end-to-end smoke

**Files:**
- Modify: `frontend/static/styles.css` (append admin-area styles)
- Create: `.env.example`
- Modify: `README.md`

- [ ] **Step 1: Append admin-area styles to `frontend/static/styles.css`**

Append (do not replace existing rules):

```css
/* --- Admin --- */

.admin-banner {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.5rem 0.85rem;
  margin: 0 0 1.5rem;
  font-size: 0.95rem;
  color: var(--muted);
}
.admin-banner strong { color: var(--fg); }

.link-button {
  background: none;
  border: none;
  padding: 0;
  color: var(--accent);
  cursor: pointer;
  font: inherit;
  text-decoration: underline;
}

.admin-form {
  display: grid;
  gap: 1rem;
  max-width: 100%;
}
.admin-form label {
  display: grid;
  gap: 0.35rem;
  font-weight: 500;
}
.admin-form input,
.admin-form textarea {
  font: inherit;
  padding: 0.5rem 0.65rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--fg);
  width: 100%;
}
.admin-form button {
  justify-self: start;
  padding: 0.55rem 1rem;
  border-radius: 8px;
  border: 1px solid var(--accent);
  background: var(--accent);
  color: var(--bg);
  font-weight: 500;
  cursor: pointer;
}

.admin-list {
  list-style: none;
  padding: 0;
  display: grid;
  gap: 0.5rem;
}
.admin-list li {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0.55rem 0.85rem;
}

.error {
  color: #b91c1c;
  background: #fee2e2;
  padding: 0.55rem 0.85rem;
  border-radius: 6px;
}
@media (prefers-color-scheme: dark) {
  .error { color: #fecaca; background: #3f1d1d; }
}
```

- [ ] **Step 2: Create `.env.example`**

```bash
# .env.example
ENV=dev
SECRET_KEY=change-me-to-a-long-random-string
DATABASE_URL=sqlite:///./site.db

# Optional: pre-fill the create-admin CLI
# ADMIN_USERNAME=
# ADMIN_PASSWORD=
```

- [ ] **Step 3: Rewrite `README.md`**

```markdown
# Personal portfolio

A small FastAPI + Jinja site with four public pages (home, projects, contact, resume) and an admin area to edit content. SQLite for storage.

## Quick start

```bash
uv sync
cp .env.example .env                            # then edit SECRET_KEY at minimum
uv run python -m backend.cli create-admin       # creates the single admin user
uv run python main.py                           # serves http://127.0.0.1:8000
```

Sign in at <http://127.0.0.1:8000/admin/login>.

## Layout

```
backend/                 Python app
  app.py                 FastAPI factory + middleware + seed
  settings.py            env-var config (pydantic-settings)
  db.py                  SQLAlchemy engine + Session + get_db dep
  models.py              ORM models
  auth.py                password hashing + CSRF helpers
  routes/public.py       /, /projects, /contact, /resume
  routes/admin.py        /admin/* — auth-gated CRUD
  cli.py                 `python -m backend.cli create-admin`
frontend/
  templates/             Jinja templates (public/ and admin/)
  static/styles.css      single stylesheet
tests/                   pytest suite
main.py                  uvicorn launcher (`from backend.app import app`)
```

## Run the tests

```bash
uv run pytest
```

## Editing content

Sign into `/admin`. The dashboard links to:

- **Site** — name, headline, bio, optional avatar URL
- **Projects** — full CRUD + manual ordering via a `position` field
- **Contact links** — full CRUD + ordering
- **Resume** — summary text + PDF path. Drop the actual PDF at `frontend/static/resume.pdf` and the download link appears on the public page.

## Notes

- Sessions: signed cookies via Starlette's `SessionMiddleware`. Set `SECRET_KEY` in `.env`. In `ENV=prod` the app refuses to start without it.
- CSRF: per-session token embedded in every form's hidden `csrf` field. Verified on POST.
- Single-admin: the CLI refuses to create a second user.
```

- [ ] **Step 4: Run the entire test suite**

Run: `uv run pytest -v`
Expected: every test passes (4 + 5 + ≥6 + 4 + 6 + 2 + 2 = roughly 29 tests).

- [ ] **Step 5: Manual end-to-end verification**

Run: `uv run python main.py`

In a browser:

1. `http://127.0.0.1:8000/` — public home renders seeded content (or your edits).
2. `http://127.0.0.1:8000/admin` — bounces to `/admin/login`.
3. Sign in with the admin user created via the CLI. Land on the dashboard.
4. Click **Edit site**, change the name, save. Visit `/` — new name appears.
5. Click **Manage projects**, add a new project, save. Visit `/projects` — appears.
6. Edit the project's `position`, save. List re-orders.
7. Delete the project (confirm prompt). Visit `/projects` — gone.
8. Repeat the same for **Contact links**.
9. **Edit resume**, change summary, save. Visit `/resume` — updated text.
10. Click **log out** in the admin banner. Hit `/admin` — bounced to login.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "docs: README + .env.example + admin CSS polish"
```

---

## Self-review notes

- **Spec coverage** — every section of the spec is covered: file layout (Task 3), auth flow + sessions + CSRF + bootstrap (Tasks 4, 5, 9), DB schema + seed (Tasks 2, 3), routes table (Tasks 3, 5, 6, 7, 8), settings + env (Tasks 1, 2, 5), tests (every task), verification (Task 10 step 5), out-of-scope items intentionally not implemented.
- **Symbol consistency** — `requires_admin` (auth on GET), `requires_admin_post` (auth + CSRF on POST), `ensure_csrf_token`, `rotate_csrf_token`, `verify_csrf`, `csrf_form_field` are introduced in Task 4 and used unchanged afterwards. `SESSION_KEY_USER` / `SESSION_KEY_CSRF` constants are used identically in `auth.py` and `routes/admin.py`.
- **Login CSRF nuance** — handled in Task 5: anonymous session gets a CSRF token via `ensure_csrf_token` on `GET /admin/login`; `POST /admin/login` calls `verify_csrf` directly (not via `requires_admin_post`, which would also require a logged-in user).
- **Import paths** — every templates import points at `frontend/templates`; every static reference points at `frontend/static`; `Jinja2Templates(directory=ROOT / "frontend" / "templates")` lets `{% extends "base.html" %}` and `{% extends "admin/base.html" %}` both resolve.
- **Test isolation** — every test goes through the in-memory `db_factory` fixture (Task 5 conftest); the public app's real `get_db` is overridden via `app.dependency_overrides`.
