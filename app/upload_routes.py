"""需求登记 H5 图片上传路由。"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response

from app.config import get_settings
from app.image_compress import ensure_image_within_limit
from app.image_payload import incoming_upload_limit, prepare_image_upload
from app.registrations import MAX_REGISTRATION_IMAGES, registration_store
from app.upload_token import create_upload_token, verify_upload_token
from app.wecom_jssdk import build_jssdk_config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["register-upload"])
_settings = get_settings()
_UPLOAD_BASE = _settings.register_upload_path.rstrip("/")

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


_HTML_PATH = Path(__file__).resolve().parent.parent / "static" / "register_upload.html"


def build_upload_page_url(task_id: str, userid: str) -> str:
    settings = get_settings()
    base = settings.public_base_url.rstrip("/")
    if not base:
        return ""
    token = create_upload_token(task_id, userid)
    path = settings.register_upload_path.rstrip("/")
    return f"{base}{path}?token={token}"


def _resolve_session(token: str):
    parsed = verify_upload_token(token)
    if parsed is None:
        raise HTTPException(status_code=403, detail="链接无效或已过期，请返回企业微信重新呼叫打开登记卡片")
    task_id, userid = parsed
    session = registration_store.get(task_id)
    if session is None or session.userid != userid:
        raise HTTPException(status_code=404, detail="登记会话不存在或已结束，请返回企业微信重新呼叫打开登记卡片")
    return session


@router.get(_UPLOAD_BASE, response_class=HTMLResponse)
async def register_upload_page(token: str = Query(...)) -> HTMLResponse:
    _resolve_session(token)
    if not _HTML_PATH.is_file():
        raise HTTPException(status_code=500, detail="上传页面缺失")
    return HTMLResponse(_HTML_PATH.read_text(encoding="utf-8"))


@router.get(f"{_UPLOAD_BASE}/api/status")
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
                    f"{_UPLOAD_BASE}/api/preview?token={token}&index={index - 1}"
                ),
            }
            for index, item in enumerate(session.uploaded_images, start=1)
        ],
    }


@router.get(f"{_UPLOAD_BASE}/api/jssdk-config")
async def register_jssdk_config(
    token: str = Query(...),
    url: str = Query(...),
) -> dict[str, Any]:
    _resolve_session(token)
    return build_jssdk_config(url)


@router.get(f"{_UPLOAD_BASE}/api/preview")
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


@router.post(f"{_UPLOAD_BASE}/api/image")
async def register_upload_image(
    token: str = Query(...),
    file: UploadFile = File(...),
) -> JSONResponse:
    session = _resolve_session(token)
    settings = get_settings()

    content_type = (file.content_type or "").lower()
    filename = file.filename or "upload.jpg"
    raw = await file.read()
    incoming_limit = incoming_upload_limit(
        raw,
        settings.max_upload_bytes,
        settings.max_encrypted_upload_bytes,
    )
    if len(raw) > incoming_limit:
        raise HTTPException(
            status_code=400,
            detail=(
                f"单张图片不能超过 {incoming_limit // (1024 * 1024)}MB"
                if incoming_limit == settings.max_upload_bytes
                else f"加密图片不能超过 {incoming_limit // (1024 * 1024)}MB"
            ),
        )
    try:
        raw, filename = prepare_image_upload(
            raw,
            filename,
            content_type,
            session.userid,
        )
        raw, filename = ensure_image_within_limit(
            raw,
            filename,
            settings.max_upload_bytes,
        )
    except ValueError as exc:
        logger.warning(
            "拒绝上传: content_type=%s filename=%s size=%s reason=%s",
            content_type,
            filename,
            len(raw),
            exc,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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


@router.post(f"{_UPLOAD_BASE}/api/image/delete")
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
