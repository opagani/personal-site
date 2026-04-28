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
