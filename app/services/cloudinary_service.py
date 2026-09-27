import hashlib
import time

import httpx
from fastapi import HTTPException, UploadFile, status

from app.core.config import get_settings

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


async def upload_institution_logo(logo: UploadFile | None) -> str | None:
    if logo is None or not logo.filename:
        return None

    settings = get_settings()
    if not ALLOWED_IMAGE_TYPES.get(logo.content_type or ""):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Logo must be a JPG, PNG or WebP image")

    content = await logo.read(settings.max_logo_bytes + 1)
    if len(content) > settings.max_logo_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Logo must be 2 MB or smaller")

    if not settings.cloudinary_cloud_name:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Cloudinary is not configured")

    data = {"folder": settings.cloudinary_institution_folder}
    if settings.cloudinary_upload_preset:
        data["upload_preset"] = settings.cloudinary_upload_preset
    elif settings.cloudinary_api_key and settings.cloudinary_api_secret:
        timestamp = str(int(time.time()))
        data["api_key"] = settings.cloudinary_api_key
        data["timestamp"] = timestamp
        data["signature"] = _signature(
            {
                "folder": settings.cloudinary_institution_folder,
                "timestamp": timestamp,
            },
            settings.cloudinary_api_secret,
        )
    else:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Cloudinary upload credentials are not configured")

    url = f"https://api.cloudinary.com/v1_1/{settings.cloudinary_cloud_name}/image/upload"
    files = {"file": (logo.filename, content, logo.content_type)}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, data=data, files=files)

    if response.status_code >= 400:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Cloudinary rejected the logo upload")

    secure_url = response.json().get("secure_url")
    if not secure_url:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Cloudinary did not return a logo URL")
    return str(secure_url)


def _signature(params: dict[str, str], api_secret: str) -> str:
    payload = "&".join(f"{key}={value}" for key, value in sorted(params.items()) if value)
    return hashlib.sha1(f"{payload}{api_secret}".encode("utf-8")).hexdigest()
