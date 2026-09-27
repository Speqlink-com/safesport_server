from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.auth import router as auth_router
from app.api.institutions import admin_router, catalog_router
from app.core.config import get_settings

settings = get_settings()
app = FastAPI(title="SafeSport API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(catalog_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
Path(settings.uploads_dir).mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.uploads_dir), name="uploads")


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}
