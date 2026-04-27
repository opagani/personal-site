# Auth + SQLite + backend/frontend folder split

**Date:** 2026-04-27
**Status:** Design — pending implementation plan

## Context

The current portfolio site (FastAPI + Jinja, four pages) keeps all editable copy in `content.py`. Editing the site means editing Python and restarting. The user wants to evolve it into a more "real" web app:

1. **Admin auth** — sign in to an `/admin` area to edit content from the browser.
2. **SQLite database** — content lives in a DB; the public site reads from it.
3. **Folder split** — Python backend separated from templates/static, both still served by one FastAPI process.

The public-facing site must stay identical on first boot (placeholder values seeded from the current `content.py`), then become editable through the admin UI.

## Architecture

One FastAPI process. Server-rendered HTML for both public and admin pages — no JS framework. Auth via signed-cookie sessions; admin POSTs are CSRF-protected via a per-session token. SQLite database file (`site.db`) persisted on disk, accessed through SQLAlchemy 2.0 (sync).

### Folder layout

```
advanced-claude/
├── backend/                  # all Python
│   ├── __init__.py
│   ├── app.py                # FastAPI factory: middleware, mounts, routers
│   ├── settings.py           # pydantic-settings: SECRET_KEY, DB path, ADMIN_*
│   ├── db.py                 # engine, SessionLocal, Base, get_db dependency
│   ├── models.py             # User, SiteMeta, Project, Link, ResumeMeta
│   ├── auth.py               # hash/verify, requires_admin, CSRF helpers
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── public.py         # GET /, /projects, /contact, /resume
│   │   └── admin.py          # GET/POST /admin/login, /admin/logout, dashboard, CRUD
│   └── cli.py                # `python -m backend.cli create-admin`
├── frontend/
│   ├── templates/
│   │   ├── base.html
│   │   ├── public/
│   │   │   ├── home.html
│   │   │   ├── projects.html
│   │   │   ├── contact.html
│   │   │   └── resume.html
│   │   └── admin/
│   │       ├── login.html
│   │       ├── dashboard.html
│   │       ├── site_form.html
│   │       ├── project_list.html
│   │       ├── project_form.html
│   │       ├── link_list.html
│   │       ├── link_form.html
│   │       └── resume_form.html
│   └── static/
│       └── styles.css
├── tests/
│   ├── conftest.py           # in-memory DB fixture, TestClient, signed-in client
│   ├── test_public.py
│   ├── test_auth.py
│   └── test_admin_crud.py
├── main.py                   # `from backend.app import app` + uvicorn launcher
├── site.db                   # gitignored
├── .env                      # gitignored
├── .env.example
└── pyproject.toml
```

`content.py` is **deleted** as part of the migration; its values seed `site_meta` and `resume_meta` on first run.

## Auth

### Flow

```
GET  /admin/login   → render login form (with CSRF hidden field)
POST /admin/login   → verify password; set session {user_id, csrf}; 303 → /admin
POST /admin/logout  → clear session; 303 → /
GET  /admin*        → requires_admin dep: 303 → /admin/login if no session
POST /admin/*       → requires_admin + CSRF token check
```

### Sessions

Starlette's `SessionMiddleware` — signed-cookie sessions. Stored value: `{"user_id": int, "csrf": str}`.

- `HttpOnly`, `SameSite=lax`. `Secure` flag is on whenever `settings.env != "dev"`.
- Lifetime: 7 days, sliding (cookie reissued on each request).
- Signed with `SECRET_KEY` from env. If unset and env is `dev`, a random key is generated at process start with a loud `WARNING: SECRET_KEY not set, using ephemeral key (sessions die on restart)` log line. Production startup with no `SECRET_KEY` aborts with a clear error.

### Password hashing

`argon2-cffi`, default parameters. `auth.py` exposes:

- `hash_password(plain: str) -> str`
- `verify_password(stored_hash: str, plain: str) -> bool`

### CSRF

Per-session token. Generated on first session creation (any GET that touches `/admin/login` or any admin-related route — see below) and rotated on successful login. Stored in the session alongside `user_id` (which may be absent for anonymous sessions). Every form template — including the login form — renders `<input type="hidden" name="csrf" value="{{ csrf_token }}">`.

- `GET /admin/login` ensures an anonymous session with a `csrf` value exists, so the login form has a token to embed.
- `POST /admin/login` verifies the `csrf` field against the anonymous session's token. On success, `user_id` is added to the session and `csrf` is rotated.
- `POST /admin/*` (authenticated) verifies the `csrf` field against the session token via `secrets.compare_digest`. Mismatch → `403 Forbidden`.
- `POST /admin/logout` requires a valid session and CSRF, same as other admin POSTs.
- All GET routes are CSRF-exempt.

### Admin bootstrap

The admin user is created out-of-band — never via a public route.

- **CLI** (primary): `uv run python -m backend.cli create-admin`. Reads `ADMIN_USERNAME` and `ADMIN_PASSWORD` from env if both are set; otherwise prompts interactively. Hashes and inserts a row into `users`. Refuses to create a second admin (single-user system).
- **Startup hint**: if `users` is empty, log one line: `No admin user. Run: uv run python -m backend.cli create-admin`. The site still serves public pages; `/admin/login` shows a "Not configured" message instead of a login form.

`.env.example` documents `SECRET_KEY`, optional `ADMIN_USERNAME`, optional `ADMIN_PASSWORD`, optional `DATABASE_URL` (default `sqlite:///./site.db`), and `ENV` (`dev` or `prod`).

## Database

### Schema (SQLAlchemy 2.0 declarative)

```
users
  id              INTEGER PK
  username        TEXT UNIQUE NOT NULL
  password_hash   TEXT NOT NULL
  created_at      DATETIME NOT NULL DEFAULT now()

site_meta                          -- singleton (id always 1)
  id          INTEGER PK
  name        TEXT NOT NULL
  headline    TEXT NOT NULL
  bio         TEXT NOT NULL
  avatar_url  TEXT NULL

projects
  id           INTEGER PK
  title        TEXT NOT NULL
  description  TEXT NOT NULL
  link         TEXT NULL
  position     INTEGER NOT NULL DEFAULT 0
  created_at   DATETIME NOT NULL DEFAULT now()
  updated_at   DATETIME NOT NULL DEFAULT now()

links                              -- contact / social links
  id        INTEGER PK
  label     TEXT NOT NULL
  url       TEXT NOT NULL
  position  INTEGER NOT NULL DEFAULT 0

resume_meta                        -- singleton (id always 1)
  id         INTEGER PK
  summary    TEXT NOT NULL
  pdf_path   TEXT NULL              -- e.g. "/static/resume.pdf"
```

Two singleton tables (`site_meta`, `resume_meta`) keep the admin UI simple — one form per section, no list/create/delete.

### Migrations

`Base.metadata.create_all(engine)` runs on app startup. No Alembic — when the first column needs to change without losing data, that's the time to add it. Out of scope here.

### Seed on first run

After `create_all`, in a single transaction:

- If `site_meta` is empty → insert `id=1` with the placeholder values currently in `content.py` (name `"Your Name"`, etc.).
- If `resume_meta` is empty → insert `id=1` with placeholder summary and `pdf_path = "/static/resume.pdf"`.
- `projects` and `links` start empty.

This guarantees the public site renders identical content on first boot.

### Per-request session

`get_db` FastAPI dependency yields a SQLAlchemy `Session` per request and closes on exit. SQLite handles its own concurrency — no pool tuning.

## Routes

### Public

| Method | Path        | Loads                                  | Renders                  |
|--------|-------------|----------------------------------------|--------------------------|
| GET    | `/`         | `site_meta`                            | `public/home.html`       |
| GET    | `/projects` | `site_meta`, all projects (ordered)    | `public/projects.html`   |
| GET    | `/contact`  | `site_meta`, all links (ordered)       | `public/contact.html`    |
| GET    | `/resume`   | `site_meta`, `resume_meta`, PDF check  | `public/resume.html`     |

Templates use the same attribute access as before (`{{ site.name }}`, `{{ p.title }}`), so they work unchanged against SQLAlchemy objects.

### Admin

| Method | Path                            | Purpose                                    |
|--------|---------------------------------|--------------------------------------------|
| GET    | `/admin/login`                  | Login form                                 |
| POST   | `/admin/login`                  | Verify, set session, redirect              |
| POST   | `/admin/logout`                 | Clear session, redirect                    |
| GET    | `/admin`                        | Dashboard with links to each editor        |
| GET    | `/admin/site`                   | Form pre-filled from `site_meta`           |
| POST   | `/admin/site`                   | Update `site_meta`, redirect (PRG)         |
| GET    | `/admin/projects`               | List + "new" link                          |
| GET    | `/admin/projects/new`           | Empty project form                         |
| POST   | `/admin/projects/new`           | Create, redirect                           |
| GET    | `/admin/projects/{id}`          | Edit form                                  |
| POST   | `/admin/projects/{id}`          | Update, redirect                           |
| POST   | `/admin/projects/{id}/delete`   | Delete, redirect                           |
| GET    | `/admin/links`                  | List + new                                 |
| GET    | `/admin/links/new`              | Empty link form                            |
| POST   | `/admin/links/new`              | Create, redirect                           |
| GET    | `/admin/links/{id}`             | Edit form                                  |
| POST   | `/admin/links/{id}`             | Update, redirect                           |
| POST   | `/admin/links/{id}/delete`      | Delete, redirect                           |
| GET    | `/admin/resume`                 | Form pre-filled from `resume_meta`         |
| POST   | `/admin/resume`                 | Update `resume_meta`, redirect             |

All admin POST handlers (other than `/admin/login`, which only requires the anonymous-session CSRF check) go through `requires_admin` (auth + CSRF) and return `303 See Other` after success — POST/redirect/GET.

`POST .../delete` rather than HTTP `DELETE` because HTML forms only support GET and POST. This is a deliberate choice — no JS, no XHR.

## Settings

`backend/settings.py` uses `pydantic-settings`:

```python
class Settings(BaseSettings):
    env: Literal["dev", "prod"] = "dev"
    secret_key: str | None = None
    database_url: str = "sqlite:///./site.db"
    admin_username: str | None = None
    admin_password: str | None = None
    session_max_age: int = 60 * 60 * 24 * 7  # 7 days

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
```

## Dependencies

Production:

- `fastapi` (already)
- `uvicorn[standard]` (already)
- `jinja2` (already)
- `sqlalchemy>=2.0`
- `argon2-cffi`
- `itsdangerous`
- `pydantic-settings`
- `python-multipart`

Dev:

- `pytest`
- `httpx` (for `TestClient`)

Add via `uv add` and `uv add --dev` so `pyproject.toml` and `uv.lock` update correctly.

## Testing

`tests/` runs via `uv run pytest`. Each test gets a fresh in-memory SQLite via a `get_db` dependency override.

- `test_public.py` — every public route returns 200; key strings from seeded `site_meta` appear in the body; CSS file is served.
- `test_auth.py`:
  - `GET /admin` unauthenticated → 303 to `/admin/login`.
  - `POST /admin/login` wrong password → 200 with error message; no session cookie set.
  - `POST /admin/login` correct → 303 to `/admin`, session cookie set.
  - `POST /admin/site` with no CSRF token → 403.
  - `POST /admin/site` with stale CSRF token → 403.
  - `POST /admin/site` with valid CSRF → 303 + DB row updated.
- `test_admin_crud.py` — create, edit, reorder, delete a project; confirm `/projects` reflects each change.

A signed-in `TestClient` fixture handles login + extracting the CSRF token for POST tests.

## Implementation order

Each step leaves the app bootable so the dev server's `--reload` keeps serving:

1. **Scaffold `backend/`** — empty package, `settings.py`, `db.py`, `models.py`, `app.py` factory. `main.py` not yet switched.
2. **Move assets** — templates to `frontend/templates/public/`, static to `frontend/static/`. Update `Jinja2Templates` directory and `StaticFiles` mount.
3. **Switch public routes to DB** — add `get_db`, rewrite handlers in `backend/routes/public.py`, run seed on startup, delete `content.py`.
4. **Point `main.py` at `backend.app:app`** — `uvicorn` reload picks it up.
5. **Add auth** — `auth.py`, `SessionMiddleware`, login/logout routes + templates.
6. **Add admin CRUD** — `backend/routes/admin.py` + admin templates.
7. **CLI** — `backend/cli.py` with `create-admin`.
8. **Tests + README update**.

## Verification

End-to-end smoke check after implementation:

1. `uv sync` — installs new deps.
2. `uv run python -m backend.cli create-admin` (with `.env` containing `ADMIN_*`) — creates admin row.
3. `uv run python main.py` — server starts; public pages at `:8000` look identical to today.
4. `GET /admin` → 303 to `/admin/login`. Sign in. Land on dashboard.
5. Edit site name on `/admin/site`, save. Visit `/` — new name renders.
6. Add a new project on `/admin/projects/new`. Visit `/projects` — appears in the list.
7. Reorder via `position`, delete one — public list updates.
8. POST `/admin/logout`. Hit `/admin` — bounced to login.
9. `uv run pytest` — all green.

## Out of scope

- File uploads (resume PDF stays a manual drop into `frontend/static/`).
- Image uploads for projects.
- Multi-user / roles / registration / password reset / OAuth / 2FA.
- Login rate limiting (single admin, low risk; revisit if abuse appears).
- Audit log / soft delete / change history.
- Alembic migrations.
- Deployment / hosting setup.
