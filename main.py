from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import content

BASE_DIR = Path(__file__).parent

app = FastAPI()
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

_resume_pdf = content.RESUME.get("pdf_path")
RESUME_PDF_PATH = BASE_DIR / _resume_pdf.lstrip("/") if _resume_pdf else None


def resume_pdf_available() -> bool:
    return RESUME_PDF_PATH is not None and RESUME_PDF_PATH.is_file()


@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(
        request,
        "home.html",
        {"site": content.SITE, "current_page": "home"},
    )


@app.get("/projects")
def projects(request: Request):
    return templates.TemplateResponse(
        request,
        "projects.html",
        {
            "site": content.SITE,
            "projects": content.PROJECTS,
            "current_page": "projects",
        },
    )


@app.get("/contact")
def contact(request: Request):
    return templates.TemplateResponse(
        request,
        "contact.html",
        {
            "site": content.SITE,
            "links": content.LINKS,
            "current_page": "contact",
        },
    )


@app.get("/resume")
def resume(request: Request):
    return templates.TemplateResponse(
        request,
        "resume.html",
        {
            "site": content.SITE,
            "resume": content.RESUME,
            "resume_pdf_available": resume_pdf_available(),
            "current_page": "resume",
        },
    )


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
