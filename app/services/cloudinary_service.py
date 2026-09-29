import hashlib
import logging
import time

import httpx
from fastapi import HTTPException, UploadFile, status

from app.core.config import get_settings

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
ALLOWED_MESSAGE_TYPES = {
    "image/jpeg", "image/png", "image/webp", "image/gif",
    "video/mp4", "video/webm", "application/pdf", "text/plain",
}
logger = logging.getLogger(__name__)


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
    if settings.cloudinary_api_key and settings.cloudinary_api_secret:
        timestamp = str(int(time.time()))
        signed_params = {
            "folder": settings.cloudinary_institution_folder,
            "timestamp": timestamp,
        }
        data["api_key"] = settings.cloudinary_api_key
        data["timestamp"] = timestamp
        data["signature"] = _signature(signed_params, settings.cloudinary_api_secret)
    elif settings.cloudinary_upload_preset:
        data["upload_preset"] = settings.cloudinary_upload_preset
    else:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Cloudinary upload credentials are not configured")

    url = f"https://api.cloudinary.com/v1_1/{settings.cloudinary_cloud_name}/image/upload"
    files = {"file": (logo.filename, content, logo.content_type)}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, data=data, files=files)

    if response.status_code >= 400:
        logger.warning("Cloudinary logo upload failed: %s", _cloudinary_error(response))
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Cloudinary rejected the logo upload")

    secure_url = response.json().get("secure_url")
    if not secure_url:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Cloudinary did not return a logo URL")
    return str(secure_url)


def _signature(params: dict[str, str], api_secret: str) -> str:
    payload = "&".join(f"{key}={value}" for key, value in sorted(params.items()) if value)
    return hashlib.sha1(f"{payload}{api_secret}".encode("utf-8")).hexdigest()


def _cloudinary_error(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:300]
    error = body.get("error")
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        return error["message"]
    return str(body)[:300]


async def upload_message_attachment(file: UploadFile | None) -> str | None:
    if file is None or not file.filename:
        return None
    settings = get_settings()
    if (file.content_type or "") not in ALLOWED_MESSAGE_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Attachment must be an image, video, PDF or text file")
    max_bytes = 10 * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Attachment must be 10 MB or smaller")
    if not settings.cloudinary_cloud_name:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Cloudinary is not configured")
    folder = "safesport/messages"
    data = {"folder": folder, "resource_type": "auto"}
    if settings.cloudinary_api_key and settings.cloudinary_api_secret:
        timestamp = str(int(time.time()))
        signed_params = {"folder": folder, "timestamp": timestamp}
        data["api_key"] = settings.cloudinary_api_key
        data["timestamp"] = timestamp
        data["signature"] = _signature(signed_params, settings.cloudinary_api_secret)
    elif settings.cloudinary_upload_preset:
        data["upload_preset"] = settings.cloudinary_upload_preset
    else:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Cloudinary upload credentials are not configured")
    url = f"https://api.cloudinary.com/v1_1/{settings.cloudinary_cloud_name}/auto/upload"
    files = {"file": (file.filename, content, file.content_type)}
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(url, data=data, files=files)
    if response.status_code >= 400:
        logger.warning("Cloudinary attachment upload failed: %s", _cloudinary_error(response))
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Cloudinary rejected the attachment upload")
    secure_url = response.json().get("secure_url")
    if not secure_url:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Cloudinary did not return an attachment URL")
    return str(secure_url)

ALLOWED_MOVEMENT_VIDEO_TYPES = {"video/mp4", "video/webm", "video/quicktime"}


async def upload_movement_video(file: UploadFile | None, screening_id: str) -> dict[str, object]:
    if file is None or not file.filename:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Screening video is required")
    settings = get_settings()
    if (file.content_type or "") not in ALLOWED_MOVEMENT_VIDEO_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Video must be MP4, WebM or QuickTime")
    max_bytes = 80 * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Video must be 80 MB or smaller")
    cloud_name = settings.movement_cloudinary_cloud_name or settings.cloudinary_cloud_name
    api_key = settings.movement_cloudinary_api_key or settings.cloudinary_api_key
    api_secret = settings.movement_cloudinary_api_secret or settings.cloudinary_api_secret
    upload_preset = settings.movement_cloudinary_upload_preset or settings.cloudinary_upload_preset
    folder = settings.movement_cloudinary_folder or "safesport/movement/originals"

    if not cloud_name:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Movement video Cloudinary is not configured")

    public_id = f"{folder}/{screening_id}"
    data = {"folder": folder, "public_id": public_id, "resource_type": "video"}
    if api_key and api_secret:
        timestamp = str(int(time.time()))
        signed_params = {"folder": folder, "public_id": public_id, "timestamp": timestamp}
        data["api_key"] = api_key
        data["timestamp"] = timestamp
        data["signature"] = _signature(signed_params, api_secret)
    elif upload_preset:
        data["upload_preset"] = upload_preset
    else:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Movement video Cloudinary upload credentials are not configured")
    url = f"https://api.cloudinary.com/v1_1/{cloud_name}/video/upload"
    files = {"file": (file.filename, content, file.content_type)}
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(url, data=data, files=files)
    if response.status_code >= 400:
        logger.warning("Cloudinary movement video upload failed: %s", _cloudinary_error(response))
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Cloudinary rejected the screening video")
    body = response.json()
    secure_url = body.get("secure_url")
    if not secure_url:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Cloudinary did not return a video URL")
    return {
        "video_url": str(secure_url),
        "video_public_id": str(body.get("public_id") or public_id),
        "metadata": {
            "width": body.get("width"),
            "height": body.get("height"),
            "duration_seconds": body.get("duration"),
            "format": body.get("format"),
            "bytes": body.get("bytes"),
            "resource_type": body.get("resource_type"),
        },
    }
