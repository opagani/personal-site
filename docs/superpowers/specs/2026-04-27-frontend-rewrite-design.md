# Public-site frontend rewrite — React + TypeScript + Vite

**Date:** 2026-04-27
**Status:** Design — pending implementation plan

## Context

The current site is FastAPI + Jinja end-to-end: server-rendered HTML for both the public pages (home, projects, blog list, blog post, contact, resume) and the admin area. The user wants to rewrite the **public** frontend as a single-page application using **React + TypeScript + React Router + Vite**, while keeping the **admin** area as Jinja-rendered server pages.

This is a frontend-only architectural shift. The SQLAlchemy models, auth, CSRF, comment moderation, anti-spam, CLI, and admin templates are unchanged. The backend gains a small JSON API for the public data the SPA needs and a catch-all route that serves the SPA's `index.html` for client-side navigation.

The intended outcome: visiting `http://127.0.0.1:8000/` (in production) loads the SPA, which routes between the public pages on the client; `/admin/*` continues to work exactly as today.

## Architecture

One FastAPI process. Three categories of HTTP traffic:

1. **`/api/*`** — JSON endpoints consumed by the SPA. New `backend/routes/api.py`.
2. **`/admin/*` and `/admin/login` etc.** — unchanged Jinja-rendered admin (`backend/routes/admin.py`).
3. **Everything else** — caught by a catch-all that serves `frontend-spa/dist/index.html` (the built SPA shell). New `backend/routes/spa.py`. React Router takes over on the client.

Static assets:
- `/static/*` → existing FastAPI mount over `frontend/static/` (CSS for admin, plus `resume.pdf` and the generated PDF)
- `/assets/*` → new mount over `frontend-spa/dist/assets/` (Vite's bundled JS/CSS for the SPA)

Markdown rendering for blog post bodies stays on the server. The API returns pre-rendered `body_html` so the SPA only needs to inject HTML, not run a Markdown parser. Comment author emails are still never shipped to the client.

### Dev workflow

Two processes during development:

- `uv run python main.py` — FastAPI on `127.0.0.1:8000`
- `npm run dev` (inside `frontend-spa/`) — Vite on `127.0.0.1:5173` with HMR, proxying `/api/*` and `/admin/*` to `:8000`

Developer browses `http://127.0.0.1:5173/`. The proxy keeps cookies/session intact for admin testing.

### Production build

- `npm run build` writes `frontend-spa/dist/` (an `index.html` plus `assets/*.js`/`*.css`).
- FastAPI mounts those assets and serves `index.html` from the catch-all.
- One process, one port (`8000`), no CORS.

## Folder layout

```
advanced-claude/
├── frontend-spa/                       NEW — Vite project root (Node-managed)
│   ├── index.html                      Vite entry HTML, mounts <div id="root">
│   ├── vite.config.ts                  Dev server proxy: /api + /admin → :8000
│   ├── tsconfig.json                   `strict: true`, `jsx: react-jsx`
│   ├── package.json                    react, react-dom, react-router-dom; -D vite, @vitejs/plugin-react, typescript
│   ├── package-lock.json
│   └── src/
│       ├── main.tsx                    root, theme bootstrap, <RouterProvider>
│       ├── App.tsx                     shell: <Header/> <main><Outlet/></main> <Footer/>
│       ├── routes.tsx                  createBrowserRouter([{path: "/", element: <App/>, children: [...]}, ...])
│       ├── api.ts                      typed fetch helpers (`getSite`, `getProjects`, …)
│       ├── types.ts                    Site, Project, Link, ResumeMeta, Post, PostDetail, Comment
│       ├── components/
│       │   ├── Header.tsx              nav + theme toggle (auto/light/dark)
│       │   ├── Footer.tsx              copyright + sign-in-or-edit link to /admin/login
│       │   ├── Spinner.tsx             "loading…" placeholder
│       │   └── ErrorBoundary.tsx       page-level error fallback
│       ├── pages/
│       │   ├── Home.tsx                fetches /api/site
│       │   ├── Projects.tsx            fetches /api/projects
│       │   ├── Contact.tsx             fetches /api/links
│       │   ├── Resume.tsx              fetches /api/resume; renders body_html via Markdown component
│       │   ├── BlogList.tsx            fetches /api/blog/posts
│       │   ├── BlogPost.tsx            fetches /api/blog/posts/{slug}; renders post + comments + form
│       │   └── NotFound.tsx            404 fallback for unknown client routes
│       └── styles.css                  vanilla CSS, ported from frontend/static/styles.css
│
├── backend/
│   ├── routes/
│   │   ├── api.py                      NEW — JSON endpoints listed below; absorbs all blog logic
│   │   │                               (list, detail with draft preview for admins, comment submit + anti-spam)
│   │   ├── spa.py                      NEW — catch-all returning frontend-spa/dist/index.html
│   │   ├── public.py                   DELETED
│   │   ├── blog.py                     DELETED — its handlers move to api.py with the new shapes
│   │   ├── admin.py                    unchanged
│   │   └── …
│   ├── app.py                          mount /assets, register api + spa routers
│   └── …
├── frontend/                           ONLY admin assets remain
│   ├── templates/admin/                unchanged
│   ├── templates/base.html             unchanged (used by admin templates)
│   └── static/                         admin CSS + resume PDFs
├── tests/
│   ├── test_api.py                     NEW — JSON contract for each endpoint
│   ├── test_spa_fallback.py            NEW — catch-all serves index.html with the right content-type
│   ├── test_public.py                  REWRITTEN to assert API behavior (now that public Jinja is gone)
│   ├── test_blog_public.py             REWRITTEN: removes HTML-shape assertions; keeps comment-submit anti-spam tests against POST /api/blog/posts/{slug}/comments
│   └── (others unchanged)
├── scripts/
│   └── build-frontend.sh               NEW — npm ci && npm run build
├── package.json                        OPTIONAL workspace root (none for now; SPA has its own)
├── .gitignore                          add frontend-spa/node_modules, frontend-spa/dist
└── README.md                           updated with the dev + build flow
```

`frontend/templates/public/` is **deleted** (home, projects, contact, resume, blog_list, blog_post). The admin templates and `frontend/static/styles.css` (used by admin) stay.

## JSON API surface

All under `/api/*`. JSON in / JSON out. Errors return RFC-style `{"detail": "…"}` with appropriate status codes. CORS is not configured because the SPA is same-origin in both dev (proxied) and prod (same FastAPI host).

| Method | Path                                       | Returns                                                                                          |
|--------|--------------------------------------------|--------------------------------------------------------------------------------------------------|
| GET    | `/api/site`                                | `{name, headline, bio, avatar_url}`                                                              |
| GET    | `/api/projects`                            | `[{id, title, description, link, position}]` ordered by `(position, id)`                         |
| GET    | `/api/links`                               | `[{id, label, url, position}]` ordered by `(position, id)`                                       |
| GET    | `/api/resume`                              | `{summary_html, pdf_path, pdf_available}`                                                        |
| GET    | `/api/blog/posts`                          | `[{slug, title, excerpt, published_at}]`, `published=true` only, ordered by `published_at` desc  |
| GET    | `/api/blog/posts/{slug}`                   | `{slug, title, body_html, published_at, comments: [...], comment_form_token}`                    |
| POST   | `/api/blog/posts/{slug}/comments`          | submit comment; same CSRF + honeypot + min-elapsed contract; on success returns `{ok: true}` (303 → no, the SPA handles UI) |

`comments` items in `GET /api/blog/posts/{slug}` are only the **approved** ones, shaped as `{author_name, body, created_at}` (no email). `comment_form_token` is the same per-session CSRF token the form needs; the SPA places it in the request body.

For admin draft preview (currently the public `/blog/{slug}` route returns 200 to a signed-in admin), the API behaves the same: if no user session and the post is unpublished, return `404`. The SPA renders the page either way; the BlogPost page shows a small "Draft" banner when the response includes `published: false`.

The min-elapsed timestamp is recorded server-side on `GET /api/blog/posts/{slug}` and read on the comment POST — same logic as today, just now triggered by the SPA's GET.

## SPA routes (React Router)

```
/                       → <Home/>
/projects               → <Projects/>
/blog                   → <BlogList/>
/blog/:slug             → <BlogPost/>
/contact                → <Contact/>
/resume                 → <Resume/>
*                       → <NotFound/>
```

Top-level layout (`<App/>`) renders `<Header/>` (nav + theme toggle), `<main><Outlet/></main>`, `<Footer/>` (sign-in-or-edit link). The header's nav links use React Router's `<NavLink/>` so the active page gets `aria-current="page"` (preserving today's behavior).

The footer's "Edit this site" / "Site owner? Sign in to edit" toggle currently depends on whether a session cookie is set. The SPA can't read `HttpOnly` cookies, so the footer shows the **single anonymous variant ("Site owner? Sign in to edit")** for all SPA visitors. Once they sign in at `/admin`, they're inside Jinja-land which already shows the right copy.

## Theme toggle

Lift the inline-script logic from `frontend/templates/base.html` into `src/main.tsx`:

- Apply persisted theme from `localStorage.getItem("theme")` to `<html>` BEFORE React mounts (avoid flash). Done at the top of `main.tsx` (synchronous, runs before `createRoot`).
- `<Header/>` renders the **Theme: auto/light/dark** button with the same cycle behavior, persisted to `localStorage`, no React re-render needed beyond the local label state.

CSS variables already drive theming; no changes to the values.

## Catch-all behavior

`backend/routes/spa.py` adds **one** route: `@app.get("/{full_path:path}")`. It serves `frontend-spa/dist/index.html` with `text/html`. To avoid swallowing API/admin/static URLs:

- Order: `api_router` first, `admin_router` next, `static` mount, then `spa_router` last (FastAPI matches in registration order).
- `spa.py` defensively rejects paths starting with `api/`, `admin`, `static/`, `assets/` and returns `404` for those, so a typo doesn't return HTML to a JSON client.

In **dev**, the catch-all is irrelevant: Vite serves the SPA on `:5173` and proxies `/api` + `/admin` to FastAPI. The catch-all only matters in production (when Vite has built `dist/` and FastAPI is the only host).

If `frontend-spa/dist/index.html` does not exist (i.e. nobody ran the build), the catch-all returns a `503` with a clear message: `"SPA build missing. Run: scripts/build-frontend.sh"`. Better than a 500 stack trace.

## Static asset mounts

```python
# backend/app.py
app.mount("/static", StaticFiles(directory=ROOT / "frontend" / "static"), name="static")
app.mount("/assets", StaticFiles(directory=ROOT / "frontend-spa" / "dist" / "assets"), name="assets")
```

The `/assets` mount references a directory that **may not exist** before the first build. We pre-create `frontend-spa/dist/assets/.gitkeep` so FastAPI can boot in a fresh checkout, then a real build replaces the contents.

## Anti-spam (unchanged contract)

`POST /api/blog/posts/{slug}/comments` enforces:

- CSRF token from the session (read from JSON body field `csrf`).
- Honeypot field `url` — non-empty silently 200s with `{ok: true}` and inserts nothing.
- Min-elapsed: session must have a recent `comment_form_ts` for this slug, set during the GET. Below the threshold → silent 200 + `{ok: true}`.
- Length validation (name 1–80, email 5–120 + regex shape, body 1–4000) returns `422` with structured `{detail: "..."}` so the SPA can show field errors.

The silent-success pattern is preserved: bots see exactly the same response (status + body) as a real success. The SPA renders a "Thanks — awaiting moderation" banner whenever it gets `{ok: true}`, regardless of whether the server actually inserted.

## Build / run instructions (README updates)

```bash
# Backend (existing)
uv sync
cp .env.example .env
uv run python -m backend.cli create-admin

# Frontend (new)
cd frontend-spa && npm ci && cd ..

# Dev — two processes
uv run python main.py            # FastAPI :8000  (admin + API + (later) SPA shell in prod)
( cd frontend-spa && npm run dev )  # Vite :5173 with HMR + proxy to :8000

# Production build of the SPA
scripts/build-frontend.sh        # runs `npm ci && npm run build` inside frontend-spa/
uv run python main.py            # serves /api/*, /admin/*, /static/*, and the built SPA at /
```

Everything else (`uv run pytest`, `uv run python -m backend.cli build-resume-pdf`, etc.) stays.

## Tests

- `tests/test_api.py` — every JSON endpoint:
  - shape of `/api/site`, `/api/projects`, `/api/links`, `/api/resume`
  - `/api/blog/posts` lists only published, with expected fields and ordering
  - `/api/blog/posts/{slug}` includes `body_html` and approved comments only
  - `/api/blog/posts/{slug}` 404 for draft anonymously, 200 for signed-in admin
  - 404 paths
- `tests/test_spa_fallback.py`:
  - `GET /` returns `text/html` and the body matches the built `index.html` (test fixture writes a stub `frontend-spa/dist/index.html` so the assertion is deterministic)
  - `GET /unknown/page` also returns the same HTML
  - `GET /api/nope` → 404 JSON
  - `GET /admin/login` still returns the admin login HTML
- `tests/test_blog_public.py` is rewritten to assert against `/api/blog/posts*` JSON; the comment anti-spam tests target `POST /api/blog/posts/{slug}/comments`. The form/DOM assertions are dropped (those move to SPA tests, out of scope here).
- All other tests unchanged.

SPA testing (vitest + Testing Library) is **out of scope** for this rewrite plan. Tracked as a follow-up.

## Verification (end-to-end manual)

1. `uv sync && (cd frontend-spa && npm ci) && scripts/build-frontend.sh`
2. `uv run python main.py`
3. `http://127.0.0.1:8000/` → SPA loads. Click around: `/`, `/projects`, `/blog`, `/blog/{slug}`, `/contact`, `/resume`. No full-page reloads. Theme toggle still cycles auto/light/dark.
4. `/admin/login` → Jinja login page (full-page navigation). Sign in. Edit a post. Visit `/blog/{slug}` (back in SPA) → updated content shown after the SPA refetches (or after a hard reload).
5. Comment submission on `/blog/{slug}` works; "Thanks — awaiting moderation" banner appears.
6. **Now run dev mode**: stop the prod server, `uv run python main.py` + `(cd frontend-spa && npm run dev)`. Browse `http://127.0.0.1:5173/`. Same flows; HMR reloads on SPA edits.
7. `uv run pytest` — all green.

## Out of scope

- SSR / pre-rendering for SEO. SPA blog posts won't be crawled well; revisit if discoverability becomes a goal.
- React Query / SWR / state management library. `useEffect` + `fetch` plus the typed `api.ts` is enough for this app.
- Tailwind / CSS-in-JS / any styling framework. The existing CSS is small and ported as-is.
- vitest + Testing Library setup for the SPA. Worth doing later; punted to a follow-up plan.
- Replacing the admin Jinja UI. That's a separate, much larger lift.
- Optimistic comment posting. The SPA fetches the page after a successful POST (or just shows the banner; comment is awaiting moderation anyway).
- Public RSS/Atom feed.

## Open risks

1. **Two toolchains.** A new contributor needs both `uv` and Node. README has to be explicit. Mitigated by `scripts/build-frontend.sh`.
2. **Build artifact in git or not.** Plan does **not** commit `frontend-spa/dist/` — gitignored. Whatever deploys this needs to run the build. Same trade-off most teams make.
3. **`HttpOnly` session cookie + SPA footer.** Cannot tell from the SPA whether the user is signed in, so the footer always shows the anonymous "sign in to edit" link. Acceptable; the admin nav lives behind that link anyway.
