from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import admin_router, public_router, site_router
from app.config import Settings
from app.openapi import get_openapi

settings = Settings()

app = FastAPI(title="Artificer API", version=settings.app_version)
PUBLIC_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "img-src 'self' data: https:; "
    "font-src 'self' data: https://cdn.jsdelivr.net https://fonts.gstatic.com; "
    "connect-src 'self'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)
APP_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https:; "
    "font-src 'self' data: https:; "
    "connect-src 'self'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)
DOCS_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "img-src 'self' data: https:; "
    "font-src 'self' data: https://cdn.jsdelivr.net https://fonts.gstatic.com; "
    "connect-src 'self'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)
API_CSP = "default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"


def _html_csp_for_path(path: str) -> str:
    if path == "/status":
        return PUBLIC_CSP
    if path == "/docs" or path.startswith("/docs/") or path == "/redoc":
        return DOCS_CSP
    return APP_CSP


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)

    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")

    content_type = response.headers.get("content-type", "")
    if content_type.startswith("text/html"):
        response.headers.setdefault("Content-Security-Policy", _html_csp_for_path(request.url.path))
    else:
        response.headers.setdefault("Content-Security-Policy", API_CSP)

    forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    if str(forwarded_proto).lower() == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")

    return response

static_dir = Path(__file__).resolve().parents[1] / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

app.include_router(site_router, tags=["public"])
app.include_router(admin_router, prefix="/api/admin", tags=["admin"])
app.include_router(public_router, prefix="/api", tags=["mock"])

# Override OpenAPI generator to use dynamic definitions.
# Keep a reference to the original generator to avoid recursion.
_original_get_openapi = app.openapi
app.openapi = lambda: get_openapi(app, settings, _original_get_openapi)
