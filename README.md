# Personal portfolio

A small FastAPI + Jinja site with four pages: home, projects, contact, resume.

## Run it

```bash
uv sync                       # install deps
uv run python main.py         # serves http://127.0.0.1:8000 with auto-reload
```

## Edit the content

All copy lives in `content.py`:

- `SITE` — name, headline, bio, optional avatar URL
- `PROJECTS` — list of `{title, description, link}`
- `LINKS` — contact / social links
- `RESUME` — summary text and optional PDF path

Drop a PDF at `static/resume.pdf` to enable the download button on the resume page.

## Layout

```
main.py            FastAPI app + routes
content.py         Site copy (edit me)
templates/         Jinja templates (base, home, projects, contact, resume)
static/styles.css  Single stylesheet, light + dark via prefers-color-scheme
```
