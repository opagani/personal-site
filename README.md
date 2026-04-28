# Personal portfolio

A small FastAPI + Jinja site with five public pages (home, projects, blog, contact, resume) and an admin area to edit content + moderate comments. SQLite for storage.

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
  routes/blog.py         /blog, /blog/{slug}, comment submission
  routes/admin.py        /admin/* — auth-gated CRUD + comment moderation
  markdown.py            shared Markdown → HTML helper
  blog_utils.py          slugify + unique_slug
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

## Deploy (Railway)

1. **Sign in** at <https://railway.com> with GitHub. **New Project → Deploy from GitHub** → pick this repo.
2. **Add a Volume**: service → **Volumes** → **+ New Volume**, mount path **`/data`**, 1 GB is plenty. (SQLite lives here so it survives redeploys.)
3. **Variables** (service → Variables):
   - `ENV=prod`
   - `SECRET_KEY=` — generate one locally: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
   - `DATABASE_URL=sqlite:////data/site.db` *(four slashes — absolute path inside the volume)*
4. Railway uses the included `Procfile` to start uvicorn on `$PORT`. Wait for the build to go green; click **View** to open the assigned `*.up.railway.app` URL.
5. **Bootstrap the admin user** — open the service's shell/run-command and run:
   ```
   python -m backend.cli create-admin --username <you> --password <pw>
   ```
6. Sign in at `https://<your-app>.up.railway.app/admin/login`.
7. *(Optional)* **Custom domain**: Settings → Networking → Custom Domain. HTTPS is auto-issued.

Expected cost for a low-traffic personal site: roughly $3–5/mo on Railway's usage-based pricing.
