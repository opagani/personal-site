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
def spa_fallback(full_path: str, request: Request):  # noqa: ARG001
    if any(full_path == p.rstrip("/") or full_path.startswith(p) for p in RESERVED_PREFIXES):
        raise HTTPException(status_code=404)
    if not SPA_INDEX.is_file():
        return JSONResponse(
            status_code=503,
            content={
                "detail": "SPA build missing. Run: scripts/build-frontend.sh"
            },
        )
    return FileResponse(SPA_INDEX, media_type="text/html")
