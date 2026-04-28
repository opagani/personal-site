"""Generate a styled PDF resume from the current `resume_meta.summary` (Markdown).

Used by `python -m backend.cli build-resume-pdf`. Writes to
`frontend/static/resume-generated.pdf` by default and updates the
`resume_meta.pdf_path` to point at it.
"""

from __future__ import annotations

from pathlib import Path

import markdown as _md
from sqlalchemy import select
from sqlalchemy.orm import Session
from xhtml2pdf import pisa

from backend.models import ResumeMeta, SiteMeta

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "frontend" / "static" / "resume-generated.pdf"

PRINT_CSS = """
@page {
  size: Letter;
  margin: 0.6in 0.7in;
}
body {
  font-family: Helvetica, Arial, sans-serif;
  color: #1a1a1a;
  font-size: 10.5pt;
  line-height: 1.45;
}
.header { margin-bottom: 0.3em; }
.header h1 { font-size: 20pt; margin: 0; }
.header .role { font-size: 11pt; color: #555; margin: 2pt 0 0 0; }
.contact-line { color: #555; font-size: 9.5pt; margin: 4pt 0 10pt 0; }

h2 {
  text-transform: uppercase;
  letter-spacing: 0.5pt;
  font-size: 10.5pt;
  color: #333;
  border-bottom: 0.6pt solid #999;
  padding-bottom: 1pt;
  margin-top: 14pt;
  margin-bottom: 5pt;
}
h3 {
  font-size: 11pt;
  margin: 8pt 0 1pt 0;
  color: #111;
}
p { margin: 3pt 0; }
em { color: #555; }
strong { color: #111; }
ul {
  margin: 2pt 0 4pt 14pt;
  padding: 0;
}
li { margin-bottom: 1.5pt; }
a { color: #1d4ed8; text-decoration: none; }
hr { border: 0; border-top: 0.5pt solid #ddd; margin: 6pt 0; }
"""


def _split_contact_line(html: str) -> tuple[str, str]:
    """Pull the first <p>...</p> off the rendered HTML and treat it as the
    contact line. Returns (contact_html_inner, rest_html)."""
    import re

    m = re.search(r"<p>(.*?)</p>", html, re.S)
    if not m:
        return "", html
    return m.group(1), html[m.end():]


def render_html(db: Session) -> str:
    sm = db.scalar(select(SiteMeta).where(SiteMeta.id == 1))
    rm = db.scalar(select(ResumeMeta).where(ResumeMeta.id == 1))

    body_md = (rm.summary or "") if rm else ""
    body_html = _md.markdown(body_md, extensions=["extra", "sane_lists"])
    contact_inner, rest = _split_contact_line(body_html)

    name = (sm.name if sm else "") or "Resume"
    role = (sm.headline if sm else "") or ""

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>{PRINT_CSS}</style></head>
<body>
  <div class="header">
    <h1>{name}</h1>
    {f'<p class="role">{role}</p>' if role else ''}
  </div>
  <div class="contact-line">{contact_inner}</div>
  <hr>
  {rest}
</body></html>"""


def build_pdf(db: Session, out_path: Path = DEFAULT_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    html = render_html(db)
    with open(out_path, "wb") as fh:
        result = pisa.CreatePDF(html, dest=fh)
    if result.err:
        raise RuntimeError(f"xhtml2pdf reported {result.err} error(s) generating PDF")
    return out_path


def build_pdf_and_update_db(db: Session, out_path: Path = DEFAULT_OUT) -> Path:
    """Generate the PDF and point resume_meta.pdf_path at it."""
    path = build_pdf(db, out_path)
    rm = db.scalar(select(ResumeMeta).where(ResumeMeta.id == 1))
    if rm is not None:
        # path served at /assets/<filename> — Railway's edge intercepts /static/*
        rm.pdf_path = "/assets/" + path.name
        db.commit()
    return path
