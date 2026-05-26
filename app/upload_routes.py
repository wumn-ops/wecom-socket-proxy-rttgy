"""需求登记 H5 图片上传路由。"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response

from app.config import get_settings
from app.registrations import MAX_REGISTRATION_IMAGES, registration_store
from app.upload_token import create_upload_token, verify_upload_token
from app.wecom_jssdk import build_jssdk_config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["register-upload"])

_ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/bmp",
    "image/heic",
    "image/heif",
    "application/octet-stream",
}
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".heif"}
_HTML_PATH = Path(__file__).resolve().parent.parent / "static" / "register_upload.html"


def build_upload_page_url(task_id: str, userid: str) -> str:
    settings = get_settings()
    base = settings.public_base_url.rstrip("/")
    if not base:
        return ""
    token = create_upload_token(task_id, userid)
    path = settings.register_upload_path.rstrip("/")
    return f"{base}{path}?token={token}"


def _detect_media_type(raw: bytes) -> str:
    if len(raw) >= 3 and raw[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if len(raw) >= 8 and raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(raw) >= 6 and raw[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    if len(raw) >= 2 and raw[:2] == b"BM":
        return "image/bmp"
    return "image/jpeg"


def _is_image_payload(raw: bytes, filename: str, content_type: str) -> bool:
    ct = (content_type or "").lower().split(";", 1)[0].strip()
    if ct in _ALLOWED_CONTENT_TYPES:
        return True

    ext = Path(filename or "").suffix.lower()
    if ext in _IMAGE_EXTENSIONS and raw:
        return True

    if len(raw) >= 3 and raw[:3] == b"\xff\xd8\xff":
        return True
    if len(raw) >= 8 and raw[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    if len(raw) >= 6 and raw[:6] in (b"GIF87a", b"GIF89a"):
        return True
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return True
    if len(raw) >= 2 and raw[:2] == b"BM":
        return True
    return False


def _resolve_session(token: str):
    parsed = verify_upload_token(token)
    if parsed is None:
        raise HTTPException(status_code=403, detail="链接无效或已过期，请重新发起登记")
    task_id, userid = parsed
    session = registration_store.get(task_id)
    if session is None or session.userid != userid:
        raise HTTPException(status_code=404, detail="登记会话不存在或已结束")
    return session


@router.get("/register/upload", response_class=HTMLResponse)
async def register_upload_page(token: str = Query(...)) -> HTMLResponse:
    _resolve_session(token)
    if not _HTML_PATH.is_file():
        raise HTTPException(status_code=500, detail="上传页面缺失")
    return HTMLResponse(_HTML_PATH.read_text(encoding="utf-8"))


@router.get("/register/upload/api/status")
async def register_upload_status(token: str = Query(...)) -> dict[str, Any]:
    session = _resolve_session(token)
    return {
        "demand_content": session.demand_content,
        "image_count": len(session.uploaded_images),
        "max_images": MAX_REGISTRATION_IMAGES,
        "images": [
            {
                "title": item.get("title", f"图片{index}"),
                "preview_url": (
                    f"/register/upload/api/preview?token={token}&index={index - 1}"
                ),
            }
            for index, item in enumerate(session.uploaded_images, start=1)
        ],
    }


@router.get("/register/upload/api/jssdk-config")
async def register_jssdk_config(
    token: str = Query(...),
    url: str = Query(...),
) -> dict[str, Any]:
    _resolve_session(token)
    return build_jssdk_config(url)


@router.get("/register/upload/api/preview")
async def register_upload_preview(
    token: str = Query(...),
    index: int = Query(..., ge=0),
) -> Response:
    session = _resolve_session(token)
    if index >= len(session.uploaded_images):
        raise HTTPException(status_code=404, detail="图片不存在")

    raw = base64.b64decode(session.uploaded_images[index]["image_base64"])
    return Response(
        content=raw,
        media_type=_detect_media_type(raw),
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.post("/register/upload/api/image")
async def register_upload_image(
    token: str = Query(...),
    file: UploadFile = File(...),
) -> JSONResponse:
    session = _resolve_session(token)
    settings = get_settings()

    content_type = (file.content_type or "").lower()
    filename = file.filename or "upload.jpg"
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="图片内容为空")
    if not _is_image_payload(raw, filename, content_type):
        logger.warning(
            "拒绝上传: content_type=%s filename=%s size=%s",
            content_type,
            filename,
            len(raw),
        )
        raise HTTPException(status_code=400, detail="仅支持 JPG/PNG/GIF/WebP/BMP/HEIC 图片")
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"单张图片不能超过 {settings.max_upload_bytes // (1024 * 1024)}MB",
        )

    index = len(session.uploaded_images) + 1
    ok, errmsg = registration_store.add_uploaded_image(
        session.task_id,
        title=f"图片{index}",
        image_base64=base64.b64encode(raw).decode("ascii"),
    )
    if not ok:
        raise HTTPException(status_code=400, detail=errmsg)

    logger.info(
        "H5 上传图片成功 task_id=%s count=%s",
        session.task_id,
        len(session.uploaded_images),
    )

    return JSONResponse(
        {
            "ok": True,
            "image_count": len(session.uploaded_images),
            "max_images": MAX_REGISTRATION_IMAGES,
        }
    )


@router.post("/register/upload/api/image/delete")
async def register_delete_image(
    token: str = Query(...),
    index: int = Query(..., ge=0),
) -> JSONResponse:
    session = _resolve_session(token)
    ok, errmsg = registration_store.remove_uploaded_image(session.task_id, index)
    if not ok:
        raise HTTPException(status_code=400, detail=errmsg)

    for idx, item in enumerate(session.uploaded_images, start=1):
        item["title"] = f"图片{idx}"

    return JSONResponse(
        {
            "ok": True,
            "image_count": len(session.uploaded_images),
            "max_images": MAX_REGISTRATION_IMAGES,
        }
    )
