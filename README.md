# Personal portfolio

A small site with five public pages (home, projects, blog, contact, resume) and an admin area to edit content + moderate comments. The **public site is a React + TypeScript SPA** (Vite-built) backed by a JSON API; the **admin area stays server-rendered Jinja**. SQLite for storage.

## Quick start

```bash
# Backend
uv sync
cp .env.example .env                            # then edit SECRET_KEY at minimum
uv run python -m backend.cli create-admin       # creates the single admin user

# Frontend (SPA build for production-shape serving)
( cd frontend-spa && npm ci )
scripts/build-frontend.sh                       # produces frontend-spa/dist/

# Run (single process, serves SPA + API + admin)
uv run python main.py                           # http://127.0.0.1:8000
```

Sign in at <http://127.0.0.1:8000/admin/login>.

### Dev mode (HMR for the SPA)

In one terminal:

```bash
uv run python main.py        # FastAPI on :8000 (API + admin)
```

In another:

```bash
( cd frontend-spa && npm run dev )    # Vite on :5173 with HMR + proxy to :8000
```

Then browse <http://127.0.0.1:5173/> for HMR. Admin still works at <http://127.0.0.1:5173/admin/login> (proxied to FastAPI).

## Layout

```
backend/                 Python app
  app.py                 FastAPI factory + middleware + seed; mounts /assets and SPA catch-all
  settings.py            env-var config (pydantic-settings)
  db.py                  SQLAlchemy engine + Session + get_db dep
  models.py              ORM models
  auth.py                password hashing + CSRF helpers
  routes/api.py          JSON API for the SPA (site, projects, links, resume, blog list/detail/comments)
  routes/admin.py        /admin/* — auth-gated CRUD + comment moderation (Jinja)
  routes/spa.py          catch-all that returns frontend-spa/dist/index.html
  markdown.py            shared Markdown → HTML helper
  blog_utils.py          slugify + unique_slug
  cli.py                 `python -m backend.cli create-admin` + `build-resume-pdf`
frontend/
  templates/admin/       Jinja templates for the admin area only
  static/styles.css      stylesheet for admin pages + the resume PDFs
frontend-spa/            React + TS + Vite project (public site)
  src/api.ts             typed fetch helpers, all endpoints under /api/*
  src/types.ts           shared response shapes
  src/components/        Header, Footer (theme toggle, brand, footer link)
  src/pages/             Home, Projects, Contact, Resume, BlogList, BlogPost, NotFound
  src/styles.css         vanilla CSS (ported from the old Jinja stylesheet)
tests/                   pytest suite (backend only — SPA tests TBD)
main.py                  uvicorn launcher (`from backend.app import app`)
scripts/build-frontend.sh   `npm ci && npm run build` inside frontend-spa/
```

## Run the tests

```bash
uv run pytest
```

## Editing content

Sign into `/admin`. The dashboard links to:

- **Site** — name, headline, bio, optional avatar URL
- **Blog posts** — full CRUD + draft/published toggle (see below)
- **Comments** — moderation queue (see below)
- **Projects** — full CRUD + manual ordering via a `position` field
- **Contact links** — full CRUD + ordering
- **Resume** — summary text + PDF path. Drop the actual PDF at `frontend/static/resume.pdf` and the download link appears on the public page.

## Blog & comments

- Sign into `/admin`, click **Manage blog posts** to write Markdown posts. Save as draft, then click **publish** when ready. Drafts are visible only to signed-in admin (handy for previewing); the public `/blog` lists only published posts.
- Visitors leave comments on each post page. The form has an invisible honeypot field plus a min-elapsed-time check, plus standard CSRF protection. Failed submissions look identical to successes (303 → `#thanks`) so spammers don't iterate.
- Every comment lands as **unapproved**. Approve or delete from `/admin/comments`. Approved comments appear publicly on the post page; nobody else sees the email address (it's stored, never rendered).
- Deleting a post cascades to its comments via the schema's `ON DELETE CASCADE`.

## Notes

- Sessions: signed cookies via Starlette's `SessionMiddleware`. Set `SECRET_KEY` in `.env`. In `ENV=prod` the app refuses to start without it.
- CSRF: per-session token embedded in every form's hidden `csrf` field. Verified on POST.
- Single-admin: the CLI refuses to create a second user.
- SQLite FK enforcement: `backend/db.py` registers a global `connect` listener that runs `PRAGMA foreign_keys=ON` on every SQLite connection so cascade deletes actually fire.
