# Public-site frontend rewrite — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the public site as a React + TypeScript + Vite SPA backed by a new JSON API, while keeping the admin area as Jinja-rendered server pages.

**Architecture:** Backend grows a `/api/*` JSON router (absorbing the data the public Jinja routes used to render server-side) and a catch-all `/{full_path:path}` route that returns the built SPA's `index.html` for client-side navigation. The old `routes/public.py` and `routes/blog.py` are deleted in the final cutover; their behavior moves entirely into `routes/api.py`. SPA lives under `frontend-spa/` (Vite project).

**Tech Stack:** Backend unchanged (FastAPI + SQLAlchemy + argon2 + Starlette `SessionMiddleware` + `markdown`). Frontend new: React 18, react-router-dom 6, TypeScript 5, Vite 5.

**Spec:** `docs/superpowers/specs/2026-04-27-frontend-rewrite-design.md`

---

## File structure (target)

```
backend/
  routes/
    api.py             NEW — all /api/* endpoints (site, projects, links, resume, blog list/detail/comment-submit)
    spa.py             NEW — catch-all that returns frontend-spa/dist/index.html
    public.py          DELETED in Task 7
    blog.py            DELETED in Task 7 (its handlers move to api.py with new shapes)
    admin.py           unchanged
  app.py               modified — mount /assets static, register api_router, drop public/blog routers, register spa_router LAST
  …                    other backend files unchanged

frontend-spa/          NEW — Vite project root (Node-managed)
  index.html
  vite.config.ts       proxy: /api + /admin → http://127.0.0.1:8000
  tsconfig.json        strict: true, jsx: react-jsx
  tsconfig.node.json   for vite.config.ts
  package.json         react@18, react-dom@18, react-router-dom@6; -D vite, @vitejs/plugin-react, typescript, @types/react, @types/react-dom
  package-lock.json    committed
  .gitignore           node_modules/, dist/, .vite/
  src/
    main.tsx           theme bootstrap (pre-paint), creates root, renders <RouterProvider>
    App.tsx            <Header/><main><Outlet/></main><Footer/>
    routes.tsx         createBrowserRouter([{path:"/", element:<App/>, children:[...]}])
    api.ts             typed fetch helpers
    types.ts           shared shapes
    styles.css         ported from frontend/static/styles.css
    components/
      Header.tsx       nav (NavLink) + theme toggle (auto/light/dark)
      Footer.tsx       copyright + "Site owner? Sign in to edit"
    pages/
      Home.tsx
      Projects.tsx
      Contact.tsx
      Resume.tsx
      BlogList.tsx
      BlogPost.tsx
      NotFound.tsx

scripts/
  build-frontend.sh    npm ci && npm run build inside frontend-spa/

tests/
  test_api.py          NEW — JSON contract for every /api endpoint
  test_spa_fallback.py NEW — catch-all serves index.html for non-API/non-admin paths
  test_public.py       REWRITTEN to assert against /api/site etc. (no more Jinja public)
  test_blog_public.py  REWRITTEN to assert against /api/blog/posts and POST /api/blog/posts/{slug}/comments
  …                    other tests unchanged

frontend/templates/public/  DELETED in Task 7 (admin templates stay)

README.md              new dev + build flow
.gitignore             add frontend-spa/dist + frontend-spa/node_modules
```

The SPA build artifact (`frontend-spa/dist/`) is **gitignored**. Whoever deploys must run `scripts/build-frontend.sh`.

**Strategy note on cutover:** Tasks 1–6 are all additive — they don't break the existing Jinja site. The dev server keeps working at `:8000` for the public pages throughout. The Vite dev server runs on `:5173` once Task 2 lands. Only Task 7 deletes the Jinja public routes and switches the catch-all on, completing the migration.

---

## Task 1: Backend JSON API (additive, TDD)

**Files:**
- Create: `backend/routes/api.py`
- Modify: `backend/app.py` (register `api_router`)
- Create: `tests/test_api.py`

This task is purely additive: existing public Jinja routes (`/`, `/blog`, etc.) continue to serve HTML. The new `/api/*` returns JSON. Both work in parallel.

- [ ] **Step 1: Write failing tests for the API**

```python
# tests/test_api.py
import time

import pytest
from sqlalchemy import select

from backend.models import Comment, Link, Post, Project


def _seed_blog(db_factory):
    Session = db_factory
    from datetime import datetime, timezone

    with Session() as s:
        s.add(Post(
            slug="hello",
            title="Hello",
            excerpt="X.",
            body_md="# Body\n\n**bold**",
            published=True,
            published_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        ))
        s.add(Post(slug="draft", title="Draft", body_md="d", published=False))
        s.commit()
        post_id = s.scalar(select(Post.id).where(Post.slug == "hello"))
        s.add(Comment(post_id=post_id, author_name="A", author_email="a@e.com",
                      body="approved", approved=True))
        s.add(Comment(post_id=post_id, author_name="B", author_email="b@e.com",
                      body="pending", approved=False))
        s.commit()


def test_api_site(client):
    r = client.get("/api/site")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Ada Lovelace"
    assert body["headline"] == "Mathematician"
    assert "bio" in body
    assert "avatar_url" in body


def test_api_projects(client, db_factory):
    Session = db_factory
    with Session() as s:
        s.add(Project(title="P1", description="d1", position=0))
        s.add(Project(title="P0", description="d0", position=-1))
        s.commit()

    r = client.get("/api/projects")
    assert r.status_code == 200
    rows = r.json()
    titles = [r["title"] for r in rows]
    assert titles == ["P0", "P1"]
    assert {"id", "title", "description", "link", "position"} <= rows[0].keys()


def test_api_links(client, db_factory):
    Session = db_factory
    with Session() as s:
        s.add(Link(label="GitHub", url="https://github.com/x", position=0))
        s.commit()
    r = client.get("/api/links")
    assert r.status_code == 200
    assert r.json()[0]["url"] == "https://github.com/x"


def test_api_resume(client):
    r = client.get("/api/resume")
    assert r.status_code == 200
    body = r.json()
    assert "summary_html" in body
    assert "Summary text." in body["summary_html"]
    assert "pdf_path" in body
    assert "pdf_available" in body
    # Test seed has pdf_path="/static/resume.pdf" but no real file on disk in test runs
    assert body["pdf_available"] is False


def test_api_blog_posts_lists_only_published(client, db_factory):
    _seed_blog(db_factory)
    r = client.get("/api/blog/posts")
    assert r.status_code == 200
    rows = r.json()
    slugs = [p["slug"] for p in rows]
    assert "hello" in slugs
    assert "draft" not in slugs
    assert {"slug", "title", "excerpt", "published_at"} <= rows[0].keys()


def test_api_blog_post_returns_body_html_and_only_approved_comments(client, db_factory):
    _seed_blog(db_factory)
    r = client.get("/api/blog/posts/hello")
    assert r.status_code == 200
    body = r.json()
    assert "<strong>bold</strong>" in body["body_html"]
    assert "comment_form_token" in body  # CSRF for the comment form
    bodies = [c["body"] for c in body["comments"]]
    assert "approved" in bodies
    assert "pending" not in bodies
    # Email never returned
    assert all("author_email" not in c for c in body["comments"])


def test_api_blog_draft_404_for_anonymous(client, db_factory):
    _seed_blog(db_factory)
    r = client.get("/api/blog/posts/draft")
    assert r.status_code == 404


def test_api_blog_draft_visible_to_signed_in_admin(signed_in_client, db_factory):
    _seed_blog(db_factory)
    r = signed_in_client.get("/api/blog/posts/draft")
    assert r.status_code == 200
    assert r.json()["title"] == "Draft"


def test_api_blog_unknown_slug_404(client):
    r = client.get("/api/blog/posts/no-such-thing")
    assert r.status_code == 404


# --- comment submission anti-spam ---


def test_api_comment_submission_happy_path(client, db_factory, monkeypatch):
    import backend.routes.api as api_routes
    monkeypatch.setattr(api_routes, "MIN_ELAPSED_SECONDS", 0)
    _seed_blog(db_factory)

    # GET sets the session timestamp + CSRF token
    r = client.get("/api/blog/posts/hello")
    csrf = r.json()["comment_form_token"]

    r = client.post(
        "/api/blog/posts/hello/comments",
        json={
            "csrf": csrf,
            "url": "",
            "author_name": "Alice",
            "author_email": "alice@example.com",
            "body": "Great post!",
        },
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    Session = db_factory
    with Session() as s:
        rows = s.scalars(select(Comment).where(Comment.body == "Great post!")).all()
        assert len(rows) == 1
        assert rows[0].approved is False


def test_api_comment_honeypot_silent_reject(client, db_factory, monkeypatch):
    import backend.routes.api as api_routes
    monkeypatch.setattr(api_routes, "MIN_ELAPSED_SECONDS", 0)
    _seed_blog(db_factory)

    r = client.get("/api/blog/posts/hello")
    csrf = r.json()["comment_form_token"]
    r = client.post(
        "/api/blog/posts/hello/comments",
        json={
            "csrf": csrf,
            "url": "spam-bots-fill-this",  # honeypot
            "author_name": "Bot",
            "author_email": "bot@example.com",
            "body": "buy stuff",
        },
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    Session = db_factory
    with Session() as s:
        rows = s.scalars(select(Comment).where(Comment.author_name == "Bot")).all()
        assert rows == []


def test_api_comment_fast_submit_silent_reject(client, db_factory):
    _seed_blog(db_factory)
    # MIN_ELAPSED_SECONDS=3 by default; test posts immediately.
    r = client.get("/api/blog/posts/hello")
    csrf = r.json()["comment_form_token"]
    r = client.post(
        "/api/blog/posts/hello/comments",
        json={
            "csrf": csrf,
            "url": "",
            "author_name": "Speedy",
            "author_email": "s@example.com",
            "body": "fast",
        },
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    Session = db_factory
    with Session() as s:
        assert s.scalars(select(Comment).where(Comment.author_name == "Speedy")).all() == []


def test_api_comment_oversize_body_returns_422(client, db_factory, monkeypatch):
    import backend.routes.api as api_routes
    monkeypatch.setattr(api_routes, "MIN_ELAPSED_SECONDS", 0)
    _seed_blog(db_factory)

    r = client.get("/api/blog/posts/hello")
    csrf = r.json()["comment_form_token"]
    r = client.post(
        "/api/blog/posts/hello/comments",
        json={
            "csrf": csrf,
            "url": "",
            "author_name": "Alice",
            "author_email": "alice@example.com",
            "body": "x" * 5000,
        },
    )
    assert r.status_code == 422
    assert "detail" in r.json()


def test_api_comment_invalid_email_returns_422(client, db_factory, monkeypatch):
    import backend.routes.api as api_routes
    monkeypatch.setattr(api_routes, "MIN_ELAPSED_SECONDS", 0)
    _seed_blog(db_factory)

    r = client.get("/api/blog/posts/hello")
    csrf = r.json()["comment_form_token"]
    r = client.post(
        "/api/blog/posts/hello/comments",
        json={
            "csrf": csrf,
            "url": "",
            "author_name": "Alice",
            "author_email": "not-an-email",
            "body": "hi",
        },
    )
    assert r.status_code == 422


def test_api_comment_csrf_mismatch_returns_403(client, db_factory, monkeypatch):
    import backend.routes.api as api_routes
    monkeypatch.setattr(api_routes, "MIN_ELAPSED_SECONDS", 0)
    _seed_blog(db_factory)

    client.get("/api/blog/posts/hello")  # establish session
    r = client.post(
        "/api/blog/posts/hello/comments",
        json={
            "csrf": "wrong-token",
            "url": "",
            "author_name": "Alice",
            "author_email": "alice@example.com",
            "body": "hi",
        },
    )
    assert r.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api.py -v`
Expected: every test fails with 404 (the `/api/*` router doesn't exist yet).

- [ ] **Step 3: Create `backend/routes/api.py`**

```python
# backend/routes/api.py
"""JSON API for the public SPA frontend.

Absorbs the data shapes that routes/public.py and routes/blog.py used to
render as HTML. The /api/blog/posts/{slug}/comments POST handler keeps the
exact anti-spam contract from the old form route (honeypot + min-elapsed
silent-reject + CSRF).
"""

import re
import time
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.auth import current_user, ensure_csrf_token, verify_csrf
from backend.db import get_db
from backend.markdown import render_markdown
from backend.models import Comment, Link, Post, Project, ResumeMeta, SiteMeta

ROOT = Path(__file__).resolve().parent.parent.parent

# Anti-spam tunables (test-overridable via monkeypatch)
MIN_ELAPSED_SECONDS = 3
MAX_NAME_LEN = 80
MAX_EMAIL_LEN = 120
MAX_BODY_LEN = 4000
MIN_BODY_LEN = 1
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
SESSION_KEY_FORM_TS = "comment_form_ts"

router = APIRouter(prefix="/api")


# --- helpers ---


def _resume_pdf_available(rm: ResumeMeta | None) -> bool:
    if rm is None or not rm.pdf_path:
        return False
    if not rm.pdf_path.startswith("/static/"):
        return False
    rel = rm.pdf_path[len("/static/") :]
    return (ROOT / "frontend" / "static" / rel).is_file()


def _record_form_render(request: Request, slug: str) -> None:
    request.session[SESSION_KEY_FORM_TS] = {"slug": slug, "ts": int(time.time())}


def _elapsed_too_short(request: Request, slug: str) -> bool:
    info = request.session.get(SESSION_KEY_FORM_TS)
    if not info or info.get("slug") != slug:
        return True
    return (int(time.time()) - int(info.get("ts", 0))) < MIN_ELAPSED_SECONDS


# --- read endpoints ---


@router.get("/site")
def get_site(db: Session = Depends(get_db)):
    sm = db.scalar(select(SiteMeta).where(SiteMeta.id == 1))
    if sm is None:
        raise HTTPException(404, detail="Site not configured")
    return {
        "name": sm.name,
        "headline": sm.headline,
        "bio": sm.bio,
        "avatar_url": sm.avatar_url,
    }


@router.get("/projects")
def list_projects(db: Session = Depends(get_db)):
    rows = db.scalars(select(Project).order_by(Project.position, Project.id)).all()
    return [
        {
            "id": p.id,
            "title": p.title,
            "description": p.description,
            "link": p.link,
            "position": p.position,
        }
        for p in rows
    ]


@router.get("/links")
def list_links(db: Session = Depends(get_db)):
    rows = db.scalars(select(Link).order_by(Link.position, Link.id)).all()
    return [
        {"id": l.id, "label": l.label, "url": l.url, "position": l.position}
        for l in rows
    ]


@router.get("/resume")
def get_resume(db: Session = Depends(get_db)):
    rm = db.scalar(select(ResumeMeta).where(ResumeMeta.id == 1))
    if rm is None:
        raise HTTPException(404, detail="Resume not configured")
    return {
        "summary_html": render_markdown(rm.summary),
        "pdf_path": rm.pdf_path,
        "pdf_available": _resume_pdf_available(rm),
    }


@router.get("/blog/posts")
def list_blog_posts(db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Post)
        .where(Post.published.is_(True))
        .order_by(Post.published_at.desc(), Post.id.desc())
    ).all()
    return [
        {
            "slug": p.slug,
            "title": p.title,
            "excerpt": p.excerpt,
            "published_at": p.published_at.isoformat() if p.published_at else None,
        }
        for p in rows
    ]


@router.get("/blog/posts/{slug}")
def get_blog_post(slug: str, request: Request, db: Session = Depends(get_db)):
    post = db.scalar(select(Post).where(Post.slug == slug))
    if post is None:
        raise HTTPException(404)
    if not post.published and current_user(request, db) is None:
        # Drafts hidden from anonymous viewers; visible to signed-in admin.
        raise HTTPException(404)

    _record_form_render(request, slug)

    comments = db.scalars(
        select(Comment)
        .where(Comment.post_id == post.id, Comment.approved.is_(True))
        .order_by(Comment.created_at.asc(), Comment.id.asc())
    ).all()

    return {
        "slug": post.slug,
        "title": post.title,
        "published": post.published,
        "published_at": post.published_at.isoformat() if post.published_at else None,
        "body_html": render_markdown(post.body_md),
        "comment_form_token": ensure_csrf_token(request),
        "comments": [
            {
                "author_name": c.author_name,
                "body": c.body,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in comments
        ],
    }


# --- comment submission ---


@router.post("/blog/posts/{slug}/comments")
def submit_comment(
    slug: str,
    request: Request,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    csrf = (payload.get("csrf") or "").strip()
    verify_csrf(request, csrf)  # 403 on mismatch

    post = db.scalar(select(Post).where(Post.slug == slug))
    if post is None:
        raise HTTPException(404)
    if not post.published and current_user(request, db) is None:
        raise HTTPException(404)

    # Silent-reject on honeypot or fast-submit. Same {ok: true} as success.
    if (payload.get("url") or "").strip():
        return {"ok": True}
    if _elapsed_too_short(request, slug):
        return {"ok": True}

    name = (payload.get("author_name") or "").strip()
    email = (payload.get("author_email") or "").strip()
    body = (payload.get("body") or "").strip()

    errors: list[str] = []
    if not (1 <= len(name) <= MAX_NAME_LEN):
        errors.append(f"Name must be 1–{MAX_NAME_LEN} characters.")
    if not (5 <= len(email) <= MAX_EMAIL_LEN) or not EMAIL_RE.fullmatch(email):
        errors.append("Enter a valid email address.")
    if not (MIN_BODY_LEN <= len(body) <= MAX_BODY_LEN):
        errors.append(f"Comment must be {MIN_BODY_LEN}–{MAX_BODY_LEN} characters.")

    if errors:
        raise HTTPException(status_code=422, detail=errors)

    db.add(Comment(
        post_id=post.id,
        author_name=name,
        author_email=email,
        body=body,
    ))
    db.commit()
    return {"ok": True}
```

- [ ] **Step 4: Register `api_router` in `backend/app.py`**

Add to imports and `include_router` calls in `backend/app.py`:

```python
# backend/app.py — add to imports
from backend.routes.api import router as api_router
```

```python
# backend/app.py — append after existing include_router calls
app.include_router(public_router)
app.include_router(blog_router)
app.include_router(admin_router)
app.include_router(api_router)        # NEW
```

(Order doesn't matter yet because there's no overlap with existing routes. Task 7 will reshuffle.)

- [ ] **Step 5: Run tests, expect pass**

Run: `uv run pytest tests/test_api.py -v`
Expected: 14 passed.

- [ ] **Step 6: Run full suite to confirm nothing else broke**

Run: `uv run pytest -v`
Expected: all green (existing 80 + 14 new = 94).

- [ ] **Step 7: Commit**

```bash
git add backend/routes/api.py backend/app.py tests/test_api.py
git commit -m "feat(api): JSON endpoints for site/projects/links/resume/blog (additive)"
```

---

## Task 2: Scaffold Vite + React + TypeScript project

**Files:**
- Create: `frontend-spa/package.json`
- Create: `frontend-spa/package-lock.json` (auto-generated by `npm install`)
- Create: `frontend-spa/tsconfig.json`
- Create: `frontend-spa/tsconfig.node.json`
- Create: `frontend-spa/vite.config.ts`
- Create: `frontend-spa/index.html`
- Create: `frontend-spa/.gitignore`
- Create: `frontend-spa/src/main.tsx`
- Create: `frontend-spa/src/App.tsx`
- Create: `frontend-spa/src/routes.tsx`
- Create: `frontend-spa/src/pages/Home.tsx` (stub)
- Create: `frontend-spa/src/pages/NotFound.tsx`
- Create: `frontend-spa/src/styles.css` (empty for now)
- Modify: top-level `.gitignore`

This task has no automated tests; verification is manual via the Vite dev server. Vitest will be a separate follow-up plan.

- [ ] **Step 1: Add `frontend-spa/dist` and `frontend-spa/node_modules` to top-level `.gitignore`**

Append to `.gitignore`:

```
# SPA build artifacts and tooling
frontend-spa/node_modules/
frontend-spa/dist/
frontend-spa/.vite/
```

- [ ] **Step 2: Create `frontend-spa/package.json`**

```json
{
  "name": "advanced-claude-spa",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.26.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "typescript": "^5.5.0",
    "vite": "^5.4.0"
  }
}
```

- [ ] **Step 3: Create `frontend-spa/.gitignore`**

```
node_modules/
dist/
.vite/
*.log
.DS_Store
```

- [ ] **Step 4: Create `frontend-spa/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "skipLibCheck": true,
    "isolatedModules": true,
    "esModuleInterop": true,
    "resolveJsonModule": true,
    "allowImportingTsExtensions": false,
    "noEmit": true
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

- [ ] **Step 5: Create `frontend-spa/tsconfig.node.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "skipLibCheck": true,
    "composite": true,
    "noEmit": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 6: Create `frontend-spa/vite.config.ts`**

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// FastAPI runs on :8000. The SPA dev server proxies /api and /admin so
// that cookies (session, CSRF) flow through without CORS gymnastics.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/admin": "http://127.0.0.1:8000",
      "/static": "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
```

- [ ] **Step 7: Create `frontend-spa/index.html`**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Portfolio</title>
    <link rel="stylesheet" href="/src/styles.css" />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 8: Create `frontend-spa/src/styles.css` (empty placeholder)**

```css
/* Real styles arrive in Task 4. This file exists so index.html can link to it. */
```

- [ ] **Step 9: Create `frontend-spa/src/main.tsx` with theme bootstrap**

```tsx
// frontend-spa/src/main.tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { RouterProvider } from "react-router-dom";

import { router } from "./routes";

// Apply persisted theme BEFORE React mounts to avoid a flash of the
// wrong colors. Mirrors the inline script in the old base.html.
(() => {
  const t = localStorage.getItem("theme");
  if (t === "light" || t === "dark") {
    document.documentElement.setAttribute("data-theme", t);
  }
})();

const rootEl = document.getElementById("root");
if (!rootEl) throw new Error("missing #root");

ReactDOM.createRoot(rootEl).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>,
);
```

- [ ] **Step 10: Create `frontend-spa/src/App.tsx`**

```tsx
// frontend-spa/src/App.tsx
import { Outlet } from "react-router-dom";

export default function App() {
  return (
    <>
      <main className="site-main">
        <Outlet />
      </main>
    </>
  );
}
```

(Header/Footer added in Task 4.)

- [ ] **Step 11: Create `frontend-spa/src/routes.tsx`**

```tsx
// frontend-spa/src/routes.tsx
import { createBrowserRouter } from "react-router-dom";

import App from "./App";
import Home from "./pages/Home";
import NotFound from "./pages/NotFound";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <Home /> },
      { path: "*", element: <NotFound /> },
    ],
  },
]);
```

(Other routes added in Tasks 5 and 6.)

- [ ] **Step 12: Create `frontend-spa/src/pages/Home.tsx` (stub)**

```tsx
// frontend-spa/src/pages/Home.tsx
export default function Home() {
  return (
    <section>
      <h1>Hello from the SPA</h1>
      <p>Real content arrives in Task 5.</p>
    </section>
  );
}
```

- [ ] **Step 13: Create `frontend-spa/src/pages/NotFound.tsx`**

```tsx
// frontend-spa/src/pages/NotFound.tsx
import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <section>
      <h1>Not found</h1>
      <p>
        That page doesn't exist. <Link to="/">Go home</Link>.
      </p>
    </section>
  );
}
```

- [ ] **Step 14: Install npm deps**

Run from the repo root:

```bash
( cd frontend-spa && npm install )
```

Expected: writes `frontend-spa/node_modules/` and `frontend-spa/package-lock.json`.

- [ ] **Step 15: Smoke test the dev server**

Run from the repo root in a separate terminal (or background):

```bash
( cd frontend-spa && npm run dev )
```

Expected output includes `Local: http://127.0.0.1:5173/`. Open that URL in a browser. Should see the "Hello from the SPA" stub.

Visit `http://127.0.0.1:5173/this-does-not-exist` — should see the NotFound page.

Stop the dev server with Ctrl-C when satisfied.

- [ ] **Step 16: Confirm `npm run build` succeeds**

```bash
( cd frontend-spa && npm run build )
```

Expected: writes `frontend-spa/dist/index.html` plus `frontend-spa/dist/assets/*.js` and `*.css`. Exits 0.

- [ ] **Step 17: Commit**

```bash
git add .gitignore frontend-spa/
git commit -m "feat(spa): scaffold Vite + React + TS project with router skeleton"
```

(`frontend-spa/node_modules` and `frontend-spa/dist` are gitignored, so this commits sources + the lockfile.)

---

## Task 3: Theme toggle + Header/Footer + ported CSS

**Files:**
- Modify: `frontend-spa/src/styles.css` (replace placeholder with port of `frontend/static/styles.css`)
- Create: `frontend-spa/src/components/Header.tsx`
- Create: `frontend-spa/src/components/Footer.tsx`
- Modify: `frontend-spa/src/App.tsx` (mount Header + Footer)

- [ ] **Step 1: Copy CSS**

Copy `frontend/static/styles.css` verbatim to `frontend-spa/src/styles.css`, overwriting the placeholder. The CSS is already standalone (custom properties, no preprocessor). Run:

```bash
cp frontend/static/styles.css frontend-spa/src/styles.css
```

- [ ] **Step 2: Create `frontend-spa/src/components/Header.tsx`**

```tsx
// frontend-spa/src/components/Header.tsx
import { useEffect, useState } from "react";
import { Link, NavLink } from "react-router-dom";

import { getSite } from "../api";

type Theme = "auto" | "light" | "dark";

const NAV: Array<{ to: string; label: string }> = [
  { to: "/", label: "Home" },
  { to: "/projects", label: "Projects" },
  { to: "/blog", label: "Blog" },
  { to: "/contact", label: "Contact" },
  { to: "/resume", label: "Resume" },
];

function readTheme(): Theme {
  const stored = localStorage.getItem("theme");
  return stored === "light" || stored === "dark" ? stored : "auto";
}

function applyTheme(t: Theme): void {
  if (t === "auto") {
    document.documentElement.removeAttribute("data-theme");
    localStorage.removeItem("theme");
  } else {
    document.documentElement.setAttribute("data-theme", t);
    localStorage.setItem("theme", t);
  }
}

function nextTheme(t: Theme): Theme {
  return t === "auto" ? "light" : t === "light" ? "dark" : "auto";
}

export default function Header() {
  const [siteName, setSiteName] = useState<string>("");
  const [theme, setTheme] = useState<Theme>(readTheme);

  useEffect(() => {
    let alive = true;
    getSite()
      .then((s) => {
        if (alive) setSiteName(s.name);
      })
      .catch(() => {
        /* keep blank */
      });
    return () => {
      alive = false;
    };
  }, []);

  function cycleTheme() {
    const t = nextTheme(theme);
    applyTheme(t);
    setTheme(t);
  }

  return (
    <header className="site-header">
      <Link className="brand" to="/">
        {siteName || "…"}
      </Link>
      <nav className="site-nav">
        {NAV.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            end={n.to === "/"}
            className={({ isActive }) => (isActive ? "site-nav__link--active" : "")}
          >
            {n.label}
          </NavLink>
        ))}
        <button
          type="button"
          className="theme-toggle"
          aria-label="Toggle color theme"
          onClick={cycleTheme}
        >
          Theme: {theme}
        </button>
      </nav>
    </header>
  );
}
```

(Note: `NavLink` automatically adds `aria-current="page"` to the active link by default — same accessibility behavior as the old Jinja template.)

- [ ] **Step 3: Create `frontend-spa/src/components/Footer.tsx`**

```tsx
// frontend-spa/src/components/Footer.tsx
import { useEffect, useState } from "react";

import { getSite } from "../api";

export default function Footer() {
  const [siteName, setSiteName] = useState<string>("");

  useEffect(() => {
    let alive = true;
    getSite()
      .then((s) => {
        if (alive) setSiteName(s.name);
      })
      .catch(() => {
        /* keep blank */
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <footer className="site-footer">
      <small>&copy; {siteName || ""}</small>
      <small className="site-footer__owner">
        <a href="/admin/login">Site owner? Sign in to edit</a>
      </small>
    </footer>
  );
}
```

(The SPA cannot read the `HttpOnly` session cookie, so it always shows the anonymous variant. This is documented in the spec as accepted.)

- [ ] **Step 4: Update `frontend-spa/src/App.tsx`**

```tsx
// frontend-spa/src/App.tsx
import { Outlet } from "react-router-dom";

import Footer from "./components/Footer";
import Header from "./components/Header";

export default function App() {
  return (
    <>
      <Header />
      <main className="site-main">
        <Outlet />
      </main>
      <Footer />
    </>
  );
}
```

- [ ] **Step 5: Verify dev server still works**

(In one terminal: `uv run python main.py`. In another: `( cd frontend-spa && npm run dev )`. Browse `http://127.0.0.1:5173/`.)

- Header shows the site name (fetched from `/api/site` via the proxy).
- Theme toggle cycles auto → light → dark → auto and persists across reloads.
- Footer shows the copyright + sign-in link.
- Clicking "Site owner? Sign in to edit" navigates to `/admin/login` (full-page nav out of the SPA — expected).

NOTE: `getSite` and `api.ts` don't exist yet — Task 4 creates them. So this task's verification only works in conjunction with Task 4. Implementations should commit Task 3 + Task 4 close together (or merge them in a worktree). Continuing with Task 4 immediately is recommended.

- [ ] **Step 6: Commit (will leave Header/Footer broken until Task 4)**

```bash
git add frontend-spa/src/
git commit -m "feat(spa): port styles.css and add Header/Footer/theme toggle"
```

---

## Task 4: API client + types

**Files:**
- Create: `frontend-spa/src/types.ts`
- Create: `frontend-spa/src/api.ts`

- [ ] **Step 1: Create `frontend-spa/src/types.ts`**

```ts
// frontend-spa/src/types.ts
export type Site = {
  name: string;
  headline: string;
  bio: string;
  avatar_url: string | null;
};

export type Project = {
  id: number;
  title: string;
  description: string;
  link: string | null;
  position: number;
};

export type LinkItem = {
  id: number;
  label: string;
  url: string;
  position: number;
};

export type ResumeData = {
  summary_html: string;
  pdf_path: string | null;
  pdf_available: boolean;
};

export type BlogPostSummary = {
  slug: string;
  title: string;
  excerpt: string | null;
  published_at: string | null;
};

export type BlogComment = {
  author_name: string;
  body: string;
  created_at: string | null;
};

export type BlogPostDetail = {
  slug: string;
  title: string;
  published: boolean;
  published_at: string | null;
  body_html: string;
  comment_form_token: string;
  comments: BlogComment[];
};

export type SubmitCommentInput = {
  csrf: string;
  url: string; // honeypot — always empty for real submissions
  author_name: string;
  author_email: string;
  body: string;
};
```

- [ ] **Step 2: Create `frontend-spa/src/api.ts`**

```ts
// frontend-spa/src/api.ts
import type {
  BlogPostDetail,
  BlogPostSummary,
  LinkItem,
  Project,
  ResumeData,
  Site,
  SubmitCommentInput,
} from "./types";

class ApiError extends Error {
  constructor(public status: number, public body: unknown, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(path, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  if (!r.ok) {
    let body: unknown = null;
    try {
      body = await r.json();
    } catch {
      /* ignore */
    }
    throw new ApiError(r.status, body, `GET ${path} failed: ${r.status}`);
  }
  return (await r.json()) as T;
}

async function postJson<T>(path: string, payload: unknown): Promise<T> {
  const r = await fetch(path, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) {
    let body: unknown = null;
    try {
      body = await r.json();
    } catch {
      /* ignore */
    }
    throw new ApiError(r.status, body, `POST ${path} failed: ${r.status}`);
  }
  return (await r.json()) as T;
}

export { ApiError };

export const getSite = () => getJson<Site>("/api/site");
export const getProjects = () => getJson<Project[]>("/api/projects");
export const getLinks = () => getJson<LinkItem[]>("/api/links");
export const getResume = () => getJson<ResumeData>("/api/resume");
export const listBlogPosts = () => getJson<BlogPostSummary[]>("/api/blog/posts");
export const getBlogPost = (slug: string) =>
  getJson<BlogPostDetail>(`/api/blog/posts/${encodeURIComponent(slug)}`);
export const submitComment = (slug: string, input: SubmitCommentInput) =>
  postJson<{ ok: true }>(
    `/api/blog/posts/${encodeURIComponent(slug)}/comments`,
    input,
  );
```

- [ ] **Step 3: Verify in the browser**

In dev mode (FastAPI on :8000, Vite on :5173, both running):

- Browse `http://127.0.0.1:5173/` — header should display the site name (e.g., "Oscar Pagani").
- Open DevTools → Network. You should see `GET /api/site` returning `200 application/json` with the expected body.
- Cycle the theme toggle — colors update; reload, choice persists.

- [ ] **Step 4: Commit**

```bash
git add frontend-spa/src/api.ts frontend-spa/src/types.ts
git commit -m "feat(spa): typed API client + shared types"
```

---

## Task 5: SPA pages — Home, Projects, Contact

**Files:**
- Create/replace: `frontend-spa/src/pages/Home.tsx`
- Create: `frontend-spa/src/pages/Projects.tsx`
- Create: `frontend-spa/src/pages/Contact.tsx`
- Modify: `frontend-spa/src/routes.tsx`

- [ ] **Step 1: Replace `frontend-spa/src/pages/Home.tsx`**

```tsx
// frontend-spa/src/pages/Home.tsx
import { useEffect, useState } from "react";

import { getSite } from "../api";
import type { Site } from "../types";

export default function Home() {
  const [site, setSite] = useState<Site | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getSite()
      .then((s) => alive && setSite(s))
      .catch(() => alive && setError("Could not load site info."));
    return () => {
      alive = false;
    };
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!site) return <p className="muted">Loading…</p>;

  return (
    <section className="hero">
      {site.avatar_url ? (
        <img className="avatar" src={site.avatar_url} alt={site.name} />
      ) : null}
      <h1>{site.name}</h1>
      <p className="headline">{site.headline}</p>
      <p className="bio">{site.bio}</p>
    </section>
  );
}
```

- [ ] **Step 2: Create `frontend-spa/src/pages/Projects.tsx`**

```tsx
// frontend-spa/src/pages/Projects.tsx
import { useEffect, useState } from "react";

import { getProjects } from "../api";
import type { Project } from "../types";

export default function Projects() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getProjects()
      .then((rows) => alive && setProjects(rows))
      .catch(() => alive && setError("Could not load projects."));
    return () => {
      alive = false;
    };
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!projects) return <p className="muted">Loading…</p>;

  return (
    <>
      <h1>Projects</h1>
      <ul className="project-list">
        {projects.map((p) => (
          <li key={p.id} className="project-card">
            <h2>
              {p.link ? <a href={p.link}>{p.title}</a> : p.title}
            </h2>
            <p>{p.description}</p>
          </li>
        ))}
      </ul>
    </>
  );
}
```

- [ ] **Step 3: Create `frontend-spa/src/pages/Contact.tsx`**

```tsx
// frontend-spa/src/pages/Contact.tsx
import { useEffect, useState } from "react";

import { getLinks } from "../api";
import type { LinkItem } from "../types";

export default function Contact() {
  const [links, setLinks] = useState<LinkItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getLinks()
      .then((rows) => alive && setLinks(rows))
      .catch(() => alive && setError("Could not load contact links."));
    return () => {
      alive = false;
    };
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!links) return <p className="muted">Loading…</p>;

  return (
    <>
      <h1>Contact</h1>
      <p>Easiest ways to reach me:</p>
      <ul className="link-list">
        {links.map((l) => (
          <li key={l.id}>
            <a href={l.url}>{l.label}</a>
          </li>
        ))}
      </ul>
    </>
  );
}
```

- [ ] **Step 4: Wire routes in `frontend-spa/src/routes.tsx`**

```tsx
// frontend-spa/src/routes.tsx
import { createBrowserRouter } from "react-router-dom";

import App from "./App";
import Contact from "./pages/Contact";
import Home from "./pages/Home";
import NotFound from "./pages/NotFound";
import Projects from "./pages/Projects";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <Home /> },
      { path: "projects", element: <Projects /> },
      { path: "contact", element: <Contact /> },
      { path: "*", element: <NotFound /> },
    ],
  },
]);
```

(Resume + Blog routes added in Task 6.)

- [ ] **Step 5: Verify in dev mode**

(`uv run python main.py` + `( cd frontend-spa && npm run dev )`, browse `http://127.0.0.1:5173/`.)

- Home: shows real name + headline + bio from DB.
- Click Projects in nav: 20 GitHub-imported projects render. No full page reload (URL bar updates but no flash).
- Click Contact: LinkedIn / Email / GitHub links render.
- Click an unknown URL like `/foo`: NotFound page renders.

- [ ] **Step 6: Commit**

```bash
git add frontend-spa/src/
git commit -m "feat(spa): Home / Projects / Contact pages"
```

---

## Task 6: SPA pages — Resume, BlogList, BlogPost (with comment form)

**Files:**
- Create: `frontend-spa/src/pages/Resume.tsx`
- Create: `frontend-spa/src/pages/BlogList.tsx`
- Create: `frontend-spa/src/pages/BlogPost.tsx`
- Modify: `frontend-spa/src/routes.tsx`

- [ ] **Step 1: Create `frontend-spa/src/pages/Resume.tsx`**

```tsx
// frontend-spa/src/pages/Resume.tsx
import { useEffect, useState } from "react";

import { getResume } from "../api";
import type { ResumeData } from "../types";

export default function Resume() {
  const [data, setData] = useState<ResumeData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getResume()
      .then((d) => alive && setData(d))
      .catch(() => alive && setError("Could not load resume."));
    return () => {
      alive = false;
    };
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="muted">Loading…</p>;

  return (
    <>
      <h1>Resume</h1>
      <div
        className="resume-body"
        dangerouslySetInnerHTML={{ __html: data.summary_html }}
      />
      {data.pdf_available && data.pdf_path ? (
        <p>
          <a className="button" href={data.pdf_path} download>
            Download PDF
          </a>
        </p>
      ) : (
        <p className="muted">
          PDF not yet uploaded. Drop one at <code>frontend/static/resume.pdf</code>{" "}
          to enable the download link.
        </p>
      )}
    </>
  );
}
```

The HTML in `summary_html` is generated by the trusted server-side Markdown renderer; injecting it via `dangerouslySetInnerHTML` is acceptable here.

- [ ] **Step 2: Create `frontend-spa/src/pages/BlogList.tsx`**

```tsx
// frontend-spa/src/pages/BlogList.tsx
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { listBlogPosts } from "../api";
import type { BlogPostSummary } from "../types";

function fmtDate(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export default function BlogList() {
  const [posts, setPosts] = useState<BlogPostSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    listBlogPosts()
      .then((rows) => alive && setPosts(rows))
      .catch(() => alive && setError("Could not load posts."));
    return () => {
      alive = false;
    };
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!posts) return <p className="muted">Loading…</p>;

  return (
    <>
      <h1>Blog</h1>
      {posts.length === 0 ? (
        <p className="muted">No posts yet.</p>
      ) : (
        <ul className="blog-list">
          {posts.map((p) => (
            <li key={p.slug} className="blog-list__item">
              <h2>
                <Link to={`/blog/${p.slug}`}>{p.title}</Link>
              </h2>
              {p.published_at ? (
                <p className="blog-list__date muted">
                  <time dateTime={p.published_at}>{fmtDate(p.published_at)}</time>
                </p>
              ) : null}
              {p.excerpt ? <p>{p.excerpt}</p> : null}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
```

- [ ] **Step 3: Create `frontend-spa/src/pages/BlogPost.tsx`**

```tsx
// frontend-spa/src/pages/BlogPost.tsx
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { ApiError, getBlogPost, submitComment } from "../api";
import type { BlogPostDetail } from "../types";

function fmtDate(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export default function BlogPost() {
  const { slug = "" } = useParams<{ slug: string }>();
  const [data, setData] = useState<BlogPostDetail | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Comment form local state
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [body, setBody] = useState("");
  const [hp, setHp] = useState(""); // honeypot — must stay empty
  const [submitState, setSubmitState] =
    useState<"idle" | "submitting" | "thanks">("idle");
  const [formErrors, setFormErrors] = useState<string[]>([]);

  useEffect(() => {
    let alive = true;
    setData(null);
    setNotFound(false);
    setError(null);
    getBlogPost(slug)
      .then((d) => alive && setData(d))
      .catch((e) => {
        if (!alive) return;
        if (e instanceof ApiError && e.status === 404) {
          setNotFound(true);
        } else {
          setError("Could not load post.");
        }
      });
    return () => {
      alive = false;
    };
  }, [slug]);

  if (notFound) return <p>Post not found.</p>;
  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="muted">Loading…</p>;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!data) return;
    setSubmitState("submitting");
    setFormErrors([]);
    try {
      await submitComment(slug, {
        csrf: data.comment_form_token,
        url: hp,
        author_name: name,
        author_email: email,
        body,
      });
      setSubmitState("thanks");
      // Clear visible fields. Keep honeypot empty.
      setName("");
      setEmail("");
      setBody("");
    } catch (err) {
      setSubmitState("idle");
      if (err instanceof ApiError && err.status === 422) {
        const detail = (err.body as { detail?: unknown })?.detail;
        if (Array.isArray(detail)) {
          setFormErrors(detail.map(String));
        } else {
          setFormErrors([String(detail ?? "Validation failed.")]);
        }
      } else if (err instanceof ApiError && err.status === 403) {
        setFormErrors(["Session expired. Refresh the page and try again."]);
      } else {
        setFormErrors(["Network error. Try again."]);
      }
    }
  }

  return (
    <>
      <article className="blog-post">
        {!data.published ? (
          <p className="muted">Draft — not visible to the public.</p>
        ) : null}
        <h1>{data.title}</h1>
        {data.published_at ? (
          <p className="blog-post__date muted">
            <time dateTime={data.published_at}>{fmtDate(data.published_at)}</time>
          </p>
        ) : null}
        <div
          className="blog-post__body"
          dangerouslySetInnerHTML={{ __html: data.body_html }}
        />
      </article>

      <section className="comments" aria-label="Comments">
        <h2>Comments</h2>

        {submitState === "thanks" ? (
          <p
            className="thanks-banner"
            style={{ display: "block", padding: "0.6rem 0.85rem", borderRadius: 6 }}
          >
            Thanks — your comment is awaiting moderation.
          </p>
        ) : null}

        {data.comments.length === 0 ? (
          <p className="muted">No comments yet — be the first.</p>
        ) : (
          <ul className="comment-list">
            {data.comments.map((c, i) => (
              <li key={i} className="comment">
                <p className="comment__meta">
                  <strong>{c.author_name}</strong>
                  {c.created_at ? (
                    <time className="muted" dateTime={c.created_at}>
                      {" "}
                      · {fmtDate(c.created_at)}
                    </time>
                  ) : null}
                </p>
                <p className="comment__body">{c.body}</p>
              </li>
            ))}
          </ul>
        )}

        {formErrors.length > 0 ? (
          <ul className="error">
            {formErrors.map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ul>
        ) : null}

        <form onSubmit={onSubmit} className="admin-form comment-form">
          {/* Honeypot — invisible to humans */}
          <div className="hp" aria-hidden="true">
            <label>
              Leave this field blank
              <input
                type="text"
                name="url"
                value={hp}
                onChange={(e) => setHp(e.target.value)}
                tabIndex={-1}
                autoComplete="off"
              />
            </label>
          </div>
          <label>
            Name
            <input
              name="author_name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              maxLength={80}
            />
          </label>
          <label>
            Email <span className="muted">(not published)</span>
            <input
              name="author_email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              maxLength={120}
            />
          </label>
          <label>
            Comment
            <textarea
              name="body"
              rows={5}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              required
              maxLength={4000}
            />
          </label>
          <button type="submit" disabled={submitState === "submitting"}>
            {submitState === "submitting" ? "Submitting…" : "Post comment"}
          </button>
        </form>
      </section>
    </>
  );
}
```

- [ ] **Step 4: Wire routes in `frontend-spa/src/routes.tsx`**

```tsx
// frontend-spa/src/routes.tsx
import { createBrowserRouter } from "react-router-dom";

import App from "./App";
import BlogList from "./pages/BlogList";
import BlogPost from "./pages/BlogPost";
import Contact from "./pages/Contact";
import Home from "./pages/Home";
import NotFound from "./pages/NotFound";
import Projects from "./pages/Projects";
import Resume from "./pages/Resume";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <Home /> },
      { path: "projects", element: <Projects /> },
      { path: "blog", element: <BlogList /> },
      { path: "blog/:slug", element: <BlogPost /> },
      { path: "contact", element: <Contact /> },
      { path: "resume", element: <Resume /> },
      { path: "*", element: <NotFound /> },
    ],
  },
]);
```

- [ ] **Step 5: Verify in dev mode**

- `/resume` renders the Markdown-rendered resume; "Download PDF" link works (clicks open `/static/resume-generated.pdf` via the Vite proxy).
- `/blog` lists existing published posts (or empty state).
- `/blog/{slug}` renders a post and its approved comments.
- Submitting a comment: wait ≥ 4s after the page loads (avoid the 3-second min-elapsed silent reject), submit valid name/email/body. The "Thanks — your comment is awaiting moderation" banner appears, fields clear.
- Sign into `/admin` (full-page nav), check `/admin/comments` — pending row exists. Approve. Reload `/blog/{slug}` in the SPA — comment now visible.

- [ ] **Step 6: Commit**

```bash
git add frontend-spa/src/
git commit -m "feat(spa): Resume, BlogList, and BlogPost (with comment form + anti-spam)"
```

---

## Task 7: Cutover — delete Jinja public, mount SPA, rewrite tests

**Files:**
- Create: `backend/routes/spa.py`
- Modify: `backend/app.py`
- Delete: `backend/routes/public.py`
- Delete: `backend/routes/blog.py`
- Delete: `frontend/templates/public/` (entire directory)
- Delete: `frontend/templates/base.html` references that only the public templates used (file is shared with admin so it stays)
- Rewrite: `tests/test_public.py`
- Rewrite: `tests/test_blog_public.py`
- Create: `tests/test_spa_fallback.py`
- Create: `scripts/build-frontend.sh`
- Modify: `README.md`

**Note:** `frontend/templates/base.html` is shared with the admin templates (admin templates `{% extends "base.html" %}`), so it stays. Only the `public/` subdirectory is removed.

- [ ] **Step 1: Create `backend/routes/spa.py`**

```python
# backend/routes/spa.py
"""Catch-all that serves the built SPA's index.html for any path the API
and admin routers didn't claim. Lets React Router handle client-side
navigation."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

ROOT = Path(__file__).resolve().parent.parent.parent
SPA_INDEX = ROOT / "frontend-spa" / "dist" / "index.html"

router = APIRouter()

# Path prefixes we never serve as SPA HTML — protects against typos in JSON
# clients getting back a 200 with HTML.
RESERVED_PREFIXES = ("api/", "admin", "static/", "assets/")


@router.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str, request: Request):  # noqa: ARG001 — request unused
    if any(full_path == p.rstrip("/") or full_path.startswith(p) for p in RESERVED_PREFIXES):
        raise HTTPException(status_code=404)
    if not SPA_INDEX.is_file():
        return JSONResponse(
            status_code=503,
            content={
                "detail": (
                    "SPA build missing. Run: scripts/build-frontend.sh"
                )
            },
        )
    return FileResponse(SPA_INDEX, media_type="text/html")
```

- [ ] **Step 2: Update `backend/app.py`**

Replace the existing imports and `include_router` block. The new structure mounts `/assets`, drops the old public + blog routers, registers the SPA catch-all LAST.

```python
# backend/app.py — top imports (full)
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
from backend.routes.api import router as api_router
from backend.routes.spa import router as spa_router
from backend.settings import settings

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("portfolio")
```

(Note the deletions: `from backend.routes.blog ...` and `from backend.routes.public ...` lines are removed.)

Replace the bottom of `backend/app.py` (the `app.mount` and `include_router` calls):

```python
# backend/app.py — bottom (replace existing mount + include_router calls)
app.mount("/static", StaticFiles(directory=ROOT / "frontend" / "static"), name="static")

# Vite-built SPA assets. Pre-create the directory so FastAPI boots before
# the first build (the file content gets replaced by `npm run build`).
_spa_assets_dir = ROOT / "frontend-spa" / "dist" / "assets"
_spa_assets_dir.mkdir(parents=True, exist_ok=True)
app.mount("/assets", StaticFiles(directory=_spa_assets_dir), name="assets")

app.include_router(api_router)         # /api/*
app.include_router(admin_router)       # /admin/*
app.include_router(spa_router)         # catch-all → SPA index.html (LAST)
```

(Keep `lifespan`, `_seed_singletons`, `_warn_if_no_admin`, `_resolve_secret_key`, `SessionMiddleware`, `DEFAULT_SITE`, and `DEFAULT_RESUME` exactly as they were.)

- [ ] **Step 3: Delete the old route modules**

```bash
git rm backend/routes/public.py
git rm backend/routes/blog.py
```

- [ ] **Step 4: Delete the old public Jinja templates**

```bash
git rm -r frontend/templates/public
```

(`frontend/templates/base.html` and the entire `frontend/templates/admin/` directory remain — admin still uses them.)

- [ ] **Step 5: Rewrite `tests/test_public.py`**

Replace the file entirely:

```python
# tests/test_public.py
"""SPA-era public tests. The public site is now a React SPA; the backend
serves /api/* (covered in test_api.py) and a catch-all that returns the
built SPA's index.html (covered in test_spa_fallback.py). This file keeps
the small set of cross-cutting checks that don't fit naturally into either."""


def test_static_styles_served(client):
    # frontend/static/styles.css is now used by the admin templates only,
    # but the mount must keep working.
    r = client.get("/static/styles.css")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/css")
```

- [ ] **Step 6: Rewrite `tests/test_blog_public.py`**

Replace the file entirely:

```python
# tests/test_blog_public.py
"""All blog public-facing behavior is now exercised through the JSON API.
The HTML-shape assertions moved out; what's left is the contract that
existed for both flows: drafts hidden, comment anti-spam, etc.

Most of these are also covered by tests/test_api.py, which is the
authoritative place. This file is kept as a thin alias to make sure the
old test names keep passing in CI dashboards/grep patterns; if we remove
it, nothing breaks."""

# Re-export the API tests under the historical names so a search for
# 'test_blog_public' still finds something. New tests should go in
# tests/test_api.py.

from tests.test_api import (  # noqa: F401 — re-exported for discovery
    test_api_blog_posts_lists_only_published as test_blog_list_published_only,
    test_api_blog_post_returns_body_html_and_only_approved_comments as test_blog_post_detail,
    test_api_blog_draft_404_for_anonymous as test_blog_draft_hidden,
    test_api_blog_draft_visible_to_signed_in_admin as test_blog_draft_visible_to_admin,
    test_api_comment_submission_happy_path as test_comment_submission_happy_path,
    test_api_comment_honeypot_silent_reject as test_honeypot_silent_reject,
    test_api_comment_fast_submit_silent_reject as test_fast_submit_silent_reject,
    test_api_comment_oversize_body_returns_422 as test_oversize_body_validation,
)
```

- [ ] **Step 7: Create `tests/test_spa_fallback.py`**

```python
# tests/test_spa_fallback.py
from pathlib import Path


def _spa_index_path():
    # Mirrors what backend/routes/spa.py looks at.
    return Path(__file__).resolve().parent.parent / "frontend-spa" / "dist" / "index.html"


def _ensure_spa_stub():
    """Write a deterministic stub index.html if the real build hasn't run.
    The actual prod build replaces this; tests just need *something* there."""
    p = _spa_index_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.is_file():
        p.write_text(
            "<!doctype html><html><body><div id='root'>SPA-STUB</div></body></html>",
            encoding="utf-8",
        )


def test_root_serves_spa_index_html(client):
    _ensure_spa_stub()
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    # Either the real build OR the stub. Both contain `id='root'` somewhere.
    assert "root" in r.text


def test_unknown_client_route_serves_spa_index_html(client):
    _ensure_spa_stub()
    r = client.get("/blog/some-slug")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")


def test_api_paths_are_not_swallowed(client):
    r = client.get("/api/no-such-endpoint")
    assert r.status_code == 404
    # Must be JSON-shaped, not HTML.
    assert r.headers["content-type"].startswith("application/json")


def test_admin_login_still_serves_html(client):
    r = client.get("/admin/login")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    # Admin login form text from the existing Jinja template.
    assert "Admin login" in r.text
```

- [ ] **Step 8: Create `scripts/build-frontend.sh`**

```bash
#!/usr/bin/env bash
# scripts/build-frontend.sh — install JS deps and produce frontend-spa/dist/.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$here/frontend-spa"

# `npm ci` if a lockfile exists, else `npm install` for first-time setups.
if [[ -f package-lock.json ]]; then
  npm ci
else
  npm install
fi

npm run build
echo "Built SPA → $here/frontend-spa/dist/"
```

Make it executable:

```bash
chmod +x scripts/build-frontend.sh
```

- [ ] **Step 9: Build the SPA so the live server has something to serve**

```bash
scripts/build-frontend.sh
```

Expected: writes `frontend-spa/dist/index.html` and `frontend-spa/dist/assets/*.js` and `*.css`. Exits 0.

- [ ] **Step 10: Run full test suite**

Run: `uv run pytest -v`
Expected: all green. Counts at this point:
- existing model tests: 9 (5 blog, 4 originals)
- auth tests: 13
- cli tests: 2
- markdown tests: 4
- blog utils tests: 8
- api tests: 14
- spa fallback tests: 4
- public tests (now slim): 1
- blog public tests (re-exports): 8
- admin meta tests: 4
- admin projects tests: 6
- admin links tests: 2
- admin posts/comments (test_blog_admin): 11

Roughly **86 tests**, all passing. Exact count may vary slightly by re-export deduplication; match what the runner reports.

- [ ] **Step 11: Manual end-to-end smoke against the running production-shape server**

If the dev server is still running with `--reload` and `main:app`, restart it once now so the deletions take effect cleanly:

```bash
# Stop existing dev server, then
uv run python main.py
```

Browse `http://127.0.0.1:8000/`:

- Home renders via the SPA — name, headline, bio.
- Click around: `/projects`, `/blog`, `/contact`, `/resume`. No full-page reloads.
- Direct-load `http://127.0.0.1:8000/blog/some-slug` (or any URL) — the catch-all serves `index.html` and the SPA routes correctly.
- `/admin/login` — Jinja form (full-page nav from the SPA).
- Sign in. Edit a post. Reload `/blog/{slug}` in the SPA — updated content shows.
- Submit a comment as anon (incognito), wait ≥ 4s, fill form, submit. "Thanks — awaiting moderation" banner appears. Comment lands as unapproved.
- Approve in `/admin/comments`. Reload SPA — comment visible.

- [ ] **Step 12: Update `README.md`**

Replace the `## Quick start` section with the new flow:

```markdown
## Quick start

The site is a FastAPI backend (Python) plus a React + TypeScript SPA (Node) for the public pages. Admin remains server-rendered Jinja.

```bash
# Backend
uv sync
cp .env.example .env                            # then edit SECRET_KEY at minimum
uv run python -m backend.cli create-admin       # creates the single admin user

# Frontend
( cd frontend-spa && npm ci )
scripts/build-frontend.sh                       # produces frontend-spa/dist/

# Run (single process, serves SPA + API + admin)
uv run python main.py                           # http://127.0.0.1:8000
```

### Dev mode (HMR for the SPA)

In one terminal:

```bash
uv run python main.py        # FastAPI on :8000
```

In another:

```bash
( cd frontend-spa && npm run dev )    # Vite on :5173 with proxy to :8000
```

Then browse <http://127.0.0.1:5173/> for HMR. Admin still works at <http://127.0.0.1:5173/admin/login> (proxied to FastAPI).

```

Append a new `## Frontend` section after the existing `## Layout`:

```markdown
## Frontend (SPA)

- `frontend-spa/` — Vite project, React 18 + TypeScript + react-router-dom 6.
- `src/api.ts` — typed `fetch` helpers, all endpoints under `/api/*`.
- `src/types.ts` — shared response shapes.
- `src/pages/*` — one file per route.
- `src/components/Header.tsx`, `Footer.tsx` — site chrome shared across all pages.
- Theme bootstrap is inline in `src/main.tsx` (runs before React mounts) to avoid a flash of the wrong colors.
- Build artifact (`frontend-spa/dist/`) is gitignored. Whatever deploys this needs to run `scripts/build-frontend.sh`.
```

- [ ] **Step 13: Commit**

```bash
git add -A
git commit -m "feat: cut over public site to React SPA; remove Jinja public routes"
```

(The build artifact `frontend-spa/dist/` is gitignored, so this commit only contains source changes.)

- [ ] **Step 14: Push to GitHub**

```bash
git push
```

---

## Self-review notes

**Spec coverage**:

- Architecture (FastAPI + JSON API + catch-all SPA shell) — Tasks 1, 7.
- Folder layout (`frontend-spa/`, `backend/routes/api.py`, `backend/routes/spa.py`, deletion of `routes/public.py` + `routes/blog.py`) — Tasks 1, 2, 7.
- JSON API surface (every row of the table in the spec) — Task 1 implementation + Task 1 test coverage.
- SPA routes (Home, Projects, Blog list, Blog post, Contact, Resume, NotFound) — Tasks 5, 6.
- Theme toggle pre-paint behavior — Task 2 (bootstrap in `main.tsx`) + Task 3 (Header button).
- Catch-all rejecting `/api`, `/admin`, `/static`, `/assets` — Task 7 (`spa.py` reserved prefixes) + Task 7 test (`test_api_paths_are_not_swallowed`).
- 503 fallback when SPA build is missing — Task 7 (`spa.py`).
- Anti-spam contract preserved on the JSON endpoint — Task 1 (handler) + Task 1 tests + Task 6 (SPA form sends `url` honeypot).
- Admin draft preview via session check — Task 1 (`current_user(request, db)` in `get_blog_post`).
- Footer always shows anonymous variant on SPA — Task 3 implementation + spec note.
- Build script — Task 7 (`scripts/build-frontend.sh`).
- Asset mounts (`/static` for admin assets, `/assets` for SPA bundles) — Task 7 (`backend/app.py`).
- README updates — Task 7 Step 12.
- SPA tests intentionally out of scope — restated in Task 2 note.

**Symbol consistency**:

- API helper names (`getSite`, `getProjects`, `getLinks`, `getResume`, `listBlogPosts`, `getBlogPost`, `submitComment`) defined in Task 4 and used unchanged in Tasks 3, 5, 6.
- Route module names (`api_router`, `admin_router`, `spa_router`) consistent across Task 1 and Task 7.
- Anti-spam constants (`MIN_ELAPSED_SECONDS`, `MAX_NAME_LEN`, `MAX_EMAIL_LEN`, `MAX_BODY_LEN`, `MIN_BODY_LEN`, `EMAIL_RE`, `SESSION_KEY_FORM_TS`) live at the top of `backend/routes/api.py` (Task 1); tests `monkeypatch.setattr(api_routes, "MIN_ELAPSED_SECONDS", 0)` everywhere.
- The form-state session key `SESSION_KEY_FORM_TS = "comment_form_ts"` collides on purpose with the value the old `routes/blog.py` used — keeps any in-flight session compatible during the cutover.

**No placeholders**: every code block is the full code.
