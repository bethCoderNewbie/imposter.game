"""
Player photo upload and serving (avatar photos).
Photos are stored in /app/photos/ (Docker volume) and served at /api/photos/{filename}.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/photos", tags=["photos"])

PHOTOS_DIR = Path("/app/photos")
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


@router.post("/upload")
async def upload_photo(file: UploadFile = File(...)):
    """Upload a player avatar photo. Returns the URL to use as photo_url on join."""
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, or WebP images are allowed.")

    data = await file.read()
    if len(data) > MAX_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="Photo exceeds 5 MB limit.")

    ext = "jpg" if file.content_type == "image/jpeg" else file.content_type.split("/")[1]
    filename = f"{uuid.uuid4().hex}.{ext}"
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    (PHOTOS_DIR / filename).write_bytes(data)

    return {"photo_url": f"/api/photos/{filename}"}


@router.get("/{filename}")
async def serve_photo(filename: str):
    """Serve a previously uploaded player photo."""
    # Basic path sanitisation — reject any traversal attempts
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename.")
    path = PHOTOS_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Photo not found.")
    media_type = "image/jpeg" if filename.endswith(".jpg") else f"image/{filename.rsplit('.', 1)[-1]}"
    return FileResponse(str(path), media_type=media_type)
