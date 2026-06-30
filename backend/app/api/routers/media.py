from __future__ import annotations

import os
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.constants import UPLOAD_DIR
from app.core.security import get_current_business
from app.models import Business
from app.schemas import QrisGenerateRequest, UploadResponse

router = APIRouter()

ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}


@router.post("/api/upload", response_model=UploadResponse)
async def dashboard_upload_image(
    file: UploadFile = File(...),
    business: Business = Depends(get_current_business),
):
    """POST /api/upload — save an image to uploads/ and return its public URL."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=422, detail="Only image files are accepted.")

    suffix = (os.path.splitext(file.filename or "")[1] or ".jpg").lower()
    if suffix not in ALLOWED_IMAGE_EXT:
        raise HTTPException(status_code=422, detail="Unsupported image type.")
    safe_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{suffix}"
    dest = os.path.join(UPLOAD_DIR, safe_name)
    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)

    return UploadResponse(url=f"/uploads/{safe_name}")


@router.post("/api/qris/generate", response_model=UploadResponse)
async def generate_qris(
    body: QrisGenerateRequest,
    business: Business = Depends(get_current_business),
):
    """POST /api/qris/generate — render a QRIS payload string to a PNG and return its public URL."""
    payload = (body.payload or "").strip()
    if not payload:
        raise HTTPException(status_code=422, detail="QRIS payload kosong.")
    import segno
    safe_name = f"qris_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
    dest = os.path.join(UPLOAD_DIR, safe_name)
    try:
        segno.make(payload, error="m").save(dest, scale=8, border=2)
    except Exception:
        raise HTTPException(status_code=422, detail="Gagal membuat QR dari payload QRIS.")
    return UploadResponse(url=f"/uploads/{safe_name}")
