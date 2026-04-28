# Blog with comments

**Date:** 2026-04-27
**Status:** Design — pending implementation plan

## Context

The portfolio currently has four public pages (home, projects, contact, resume) and an admin area for editing site copy / projects / links / resume. The user wants to add a **blog** with **comments** so visitors can read posts and leave moderated feedback. This builds on the existing FastAPI + Jinja + SQLite + session-auth + CSRF stack.

The core requirements decided in brainstorming:

- **Comments** are anonymous (name + email + body, no visitor accounts) and **admin-moderated** — every comment is hidden until the admin approves it.
- **Anti-spam** uses an invisible honeypot field plus a minimum elapsed-time check between form render and submission. No third-party CAPTCHA. Failed submissions silently look successful so bots don't iterate.
- **Posts** support **Markdown bodies**, a **draft/published flag**, **pretty URL slugs**, and an **optional excerpt** for the list page.

## Architecture

One FastAPI process. Server-rendered HTML for both public and admin. The blog is a third public surface (alongside the static four pages and the admin area), and comment moderation is a new admin sub-surface. New code lives under existing seams: ORM models in `backend/models.py`, public blog routes in `backend/routes/blog.py`, admin handlers appended to `backend/routes/admin.py`. Existing infrastructure — session auth, CSRF, `requires_admin` / `requires_admin_post` deps, `Jinja2Templates`, `get_db` — is reused unchanged.

The Markdown rendering helper currently in `backend/routes/public.py` is extracted to `backend/markdown.py` so both `/resume` and `/blog/{slug}` can use it.

## Schema

Two new tables, declared via SQLAlchemy 2.0 alongside the existing models. `Base.metadata.create_all(engine)` on app startup creates them; no Alembic migration. Existing data (admin user, site_meta, resume_meta, projects, links) is untouched.

```
posts
  id            INTEGER PK
  slug          TEXT UNIQUE NOT NULL
  title         TEXT NOT NULL
  excerpt       TEXT NULL                 -- short blurb for the list page
  body_md       TEXT NOT NULL             -- Markdown source
  published     BOOLEAN NOT NULL DEFAULT 0
  published_at  DATETIME NULL             -- set on first publish, never cleared
  created_at    DATETIME NOT NULL DEFAULT now()
  updated_at    DATETIME NOT NULL DEFAULT now() ON UPDATE now()

comments
  id            INTEGER PK
  post_id       INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE
  author_name   TEXT NOT NULL
  author_email  TEXT NOT NULL             -- never displayed publicly
  body          TEXT NOT NULL
  created_at    DATETIME NOT NULL DEFAULT now()
  approved      BOOLEAN NOT NULL DEFAULT 0
  approved_at   DATETIME NULL             -- set when admin approves; never cleared
```

`posts.slug` is unique. `comments.post_id` has an index.

`author_email` is stored for admin's reference only. Templates never render it.

## Routes

### Public — `backend/routes/blog.py`

| Method | Path                          | Behavior                                                                       |
|--------|-------------------------------|--------------------------------------------------------------------------------|
| GET    | `/blog`                       | Lists posts where `published = 1`, ordered by `published_at DESC`. Renders title, date, excerpt. |
| GET    | `/blog/{slug}`                | Loads the post by slug. 404 if not found, or if `published = 0` and viewer is not admin. Renders post body + approved comments + new-comment form. |
| POST   | `/blog/{slug}/comments`       | Submits a comment. CSRF + anti-spam checks. On success, inserts with `approved = 0` and 303-redirects back to `/blog/{slug}#thanks`. |

### Admin — appended to `backend/routes/admin.py`

| Method | Path                                  | Behavior                                                              |
|--------|---------------------------------------|-----------------------------------------------------------------------|
| GET    | `/admin/posts`                        | Lists all posts (drafts + published), drafts first, then by updated.  |
| GET    | `/admin/posts/new`                    | Empty post form (title, slug placeholder, excerpt, body_md, published checkbox). |
| POST   | `/admin/posts/new`                    | Create post (auto-slug if blank); redirect to `/admin/posts`.         |
| GET    | `/admin/posts/{id}`                   | Edit form pre-filled.                                                 |
| POST   | `/admin/posts/{id}`                   | Update post; redirect to `/admin/posts`.                              |
| POST   | `/admin/posts/{id}/delete`            | Delete post; cascade deletes comments; redirect.                      |
| POST   | `/admin/posts/{id}/publish`           | Toggle `published`. First flip to `True` sets `published_at = now`. Subsequent flips do not modify `published_at`. |
| GET    | `/admin/comments`                     | Moderation queue. Unapproved first, then approved-DESC. Each row links to its post. |
| POST   | `/admin/comments/{id}/approve`        | Set `approved = 1`, `approved_at = now`. Redirect to `/admin/comments`. |
| POST   | `/admin/comments/{id}/delete`         | Delete the comment. Redirect to `/admin/comments`.                    |

All admin POSTs go through `requires_admin_post` (auth + CSRF). All admin GETs go through `requires_admin`. PRG (303) on every state-changing POST.

## Anti-spam

The public comment form is the only public state-changing endpoint, so it carries the full burden:

1. **Honeypot**: the form renders `<input type="text" name="url" value="" tabindex="-1" autocomplete="off">` inside a `<div class="hp">` styled with `position:absolute; left:-10000px; height:1px; width:1px;`. Real users never see or focus this field. Bots that fill every input will populate it. On POST, if `url` is non-empty, the handler **silent-rejects** (see below).

2. **Minimum elapsed time**: when the public post page renders, the handler stores `request.session["comment_form_ts"] = {"slug": slug, "ts": int(time.time())}`. On POST, the handler computes `elapsed = now() - request.session["comment_form_ts"]["ts"]`. If `elapsed < 3` seconds, **or** the slug doesn't match, **or** the session has no `comment_form_ts`, the handler **silent-rejects**.

3. **CSRF token**: same per-session anonymous CSRF mechanism already used by the admin login. Mismatch returns 403 (not silent-reject) — bots without sessions hit a brick wall here, and real users have a session because the GET set one.

4. **Length validation**: server enforces `1 <= len(name) <= 80`, `5 <= len(email) <= 120`, `1 <= len(body) <= 4000`. Plus a basic email shape check (`re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)`). Failures **render the form with errors** (200), not silent-reject — real users need to know.

**Silent-reject** = exactly the same 303 redirect to `/blog/{slug}#thanks` as the success path, with no DB insert. From outside the server there is no observable difference between a real success and a silent reject: same status code, same `Location` header, same resulting HTML on the GET that follows. A bot that sees a 303-then-200 thank-you banner has no signal to retry with variations.

## Slug generation

When the admin creates a post and leaves the slug field blank, the server generates one:

```python
def slugify(title: str) -> str:
    s = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:80] or "post"
```

If the resulting slug already exists in `posts`, append `-2`, `-3`, etc. until unique. Admin can also type a slug directly; that value is taken verbatim (still slugified for safety, and conflict-suffixed if already taken — except when editing the same post, which keeps its slug).

## Markdown rendering

`backend/routes/public.py` currently has:

```python
def _render_markdown(text: str | None) -> str:
    if not text:
        return ""
    return _md.markdown(text, extensions=["extra", "sane_lists"])
```

Move this to `backend/markdown.py` as `render_markdown(text)` (drop the underscore prefix; it's now a public helper). Update both `routes/public.py` (resume) and `routes/blog.py` (post body) to import it. No behavior change for resume.

## Templates

Public:

- `frontend/templates/public/blog_list.html` — extends `base.html`. `<h1>Blog</h1>`, then `<article>` per post: `<h2><a href="/blog/{slug}">{title}</a></h2>`, formatted `published_at`, `{excerpt}` if present.
- `frontend/templates/public/blog_post.html` — extends `base.html`. `<article>`: title, formatted date, rendered Markdown body. Then `<section class="comments">` showing each approved comment (name + relative date + body, no email). Then a comment form with honeypot, CSRF token, name/email/body inputs, submit button. If the URL fragment is `#thanks`, show a "Thanks — your comment is awaiting moderation." banner above the form.

Admin:

- `frontend/templates/admin/post_list.html` — extends `admin/base.html`. List with status badge (Draft/Published), title (links to edit), updated date. "+ New post" button. Per-row Publish/Unpublish toggle (POST form) and Delete (POST form, with `confirm()`).
- `frontend/templates/admin/post_form.html` — title input, slug input (placeholder shows generated slug live? — out of scope; just empty + hint "leave blank to auto-generate"), excerpt textarea (1 row), body_md textarea (20+ rows, Markdown supported note), published checkbox, save button. Same form template handles new + edit.
- `frontend/templates/admin/comment_queue.html` — extends `admin/base.html`. Two sections: "Pending" (unapproved) and "Recently approved". Each row shows author_name, author_email, post title (link), body, created date, and Approve / Delete forms.

Public nav adds **Blog** between Projects and Contact in `frontend/templates/base.html`.

## Settings

No new env vars. Anti-spam constants (`MIN_ELAPSED_SECONDS = 3`, `MAX_NAME_LEN = 80`, etc.) live as module-level constants in `backend/routes/blog.py`.

## Dependencies

None new. `markdown` is already a dep.

## Testing

`tests/test_blog_public.py`:

- Empty state: `/blog` returns 200 with "no posts yet" message; `/blog/missing` 404.
- Drafts hidden: a `published=False` post is **not** in `/blog`; visiting `/blog/{its-slug}` as anonymous returns 404.
- Drafts visible to admin: same URL as `signed_in_client` returns 200.
- Comment form GET on a published post returns 200, has CSRF + honeypot fields.
- Comment POST happy path: 303 to `/blog/{slug}#thanks`, comment row exists with `approved=False`, public page does NOT yet show it.
- Honeypot filled: 200, no row inserted.
- Fast submit (`elapsed < MIN_ELAPSED_SECONDS`): 200, no row inserted.
- Length validation: oversize body returns form with error.

`tests/test_blog_admin.py`:

- `signed_in_client` post CRUD: create with auto-slug, edit slug + body, delete cascades to comments.
- Slug conflict: creating a second post with the same auto-slug appends `-2`.
- Publish toggle: first publish sets `published_at`; unpublish keeps `published_at`; re-publish does not overwrite it.
- Comment moderation: approve sets `approved=True` + `approved_at`; delete removes the row; an approved comment then shows on the public post page.

`tests/test_markdown.py` (small new file or appended to test_public.py):

- `render_markdown("**hi**")` returns `<p><strong>hi</strong></p>` (sanity, ensures the helper move didn't break anything).

## Implementation order

Each step keeps the dev server bootable.

1. **Markdown helper extraction** — move `_render_markdown` → `backend/markdown.py`. Update `routes/public.py`. Tests still pass unchanged.
2. **Models + create_all** — add `Post` and `Comment` to `backend/models.py`. App startup picks them up.
3. **Public blog routes (read only)** — `backend/routes/blog.py` with `/blog` and `/blog/{slug}` (no comment form yet). Mount in `backend/app.py`. Add Blog link to nav.
4. **Comment form + submission + anti-spam** — extend the post template + add `POST /blog/{slug}/comments`.
5. **Admin posts CRUD** — append routes + add admin/post_list.html + post_form.html. Slug auto-gen + conflict resolution.
6. **Admin comment moderation** — `/admin/comments` queue + approve/delete actions.
7. **Tests** for everything above.
8. **README touch-up** mentioning blog + moderation flow.

## Verification

End-to-end:

1. `uv run pytest` — all green.
2. `uv run python main.py`, sign in at `/admin/login`.
3. `/admin/posts/new` — write a post in Markdown, check Published, save. `/blog` shows it; `/blog/{slug}` renders the body.
4. As anonymous: `/blog/{slug}` shows form. Submit a comment → "Thanks — awaiting moderation." Comment does NOT appear on the page yet.
5. Sign in as admin → `/admin/comments` shows the pending comment. Approve. Refresh `/blog/{slug}` → comment now visible.
6. Sanity-check anti-spam manually with `curl`: `POST` with the honeypot field set should silently 303/200 with no DB row added. Submission < 3s after GET should also do nothing.

## Out of scope

- Reply threading (comments are flat).
- Editing comments by anyone.
- Email notifications to admin on new comment.
- RSS / Atom feed for `/blog`.
- Tags / categories / search.
- Pagination (current ordering is fine for low post counts; revisit at ~50+ posts).
- Gravatar / commenter avatars.
- IP logging or rate-limit-by-IP (revisit if honeypot proves insufficient).
- Migration tooling (still using `Base.metadata.create_all`).
