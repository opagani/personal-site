"""Single source of Markdown → HTML rendering for the site.

Used by the resume page and the blog.
"""

import markdown as _md


def render_markdown(text: str | None) -> str:
    if not text:
        return ""
    return _md.markdown(text, extensions=["extra", "sane_lists"])
