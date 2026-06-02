"""需求登记 H5 一站式填表路由（对齐 wecom-proxy-fkh 卡片 → H5 → 写表流程）。"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from app.config import get_settings
from app.registrations import MAX_REGISTRATION_IMAGES, registration_store
from app.smartsheet import add_demand_record
from app.system_options import parse_option_list
from app.template_cards import new_task_id
from app.upload_routes import _detect_media_type, _is_image_payload
from app.upload_token import create_upload_token, verify_upload_token
from app.wecom_jssdk import build_jssdk_config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["register-daily"])
_settings = get_settings()
_DAILY_BASE = _settings.register_daily_path.rstrip("/")
_HTML_PATH = Path(__file__).resolve().parent.parent / "static" / "register_daily.html"


def build_register_daily_page_url(userid: str) -> str:
    """生成带 token 的登记 H5 链接（欢迎卡片按钮使用）。"""
    settings = get_settings()
    base = settings.public_base_url.rstrip("/")
    if not base or not userid:
        return ""
    task_id = new_task_id()
    registration_store.create(
        task_id=task_id,
        demand_content="",
        userid=userid,
    )
    token = create_upload_token(task_id, userid)
    path = settings.register_daily_path.rstrip("/")
    return f"{base}{path}?token={token}"


class DailyRegisterSubmitBody(BaseModel):
    demand_content: str = Field(..., min_length=1, max_length=2000)
    system: str = Field(..., min_length=1, max_length=100)


def _resolve_session(token: str):
    parsed = verify_upload_token(token)
    if parsed is None:
        raise HTTPException(status_code=403, detail="链接无效或已过期，请返回企业微信重新打开")
    task_id, userid = parsed
    session = registration_store.get(task_id)
    if session is None or session.userid != userid:
        raise HTTPException(status_code=404, detail="登记会话不存在或已结束")
    return session


async def _notify_register_success(request: Request, userid: str) -> None:
    settings = get_settings()
    message = settings.register_daily_success_message.strip()
    if not message:
        return

    bot_service = getattr(request.app.state, "bot_service", None)
    handler = bot_service.handler if bot_service is not None else None
    if handler is None:
        logger.warning("登记提交成功但 WebSocket 未就绪，跳过企微提醒 userid=%s", userid)
        return

    sent = await handler.notify_user_markdown(userid, message)
    if not sent:
        logger.warning("登记成功提醒发送失败 userid=%s", userid)


@router.get(_DAILY_BASE, response_class=HTMLResponse)
async def register_daily_page(token: str = Query(...)) -> HTMLResponse:
    _resolve_session(token)
    if not _HTML_PATH.is_file():
        raise HTTPException(status_code=500, detail="登记页面缺失")
    return HTMLResponse(_HTML_PATH.read_text(encoding="utf-8"))


@router.get(f"{_DAILY_BASE}/api/options")
async def register_daily_options(token: str = Query(...)) -> dict[str, Any]:
    _resolve_session(token)
    options = parse_option_list(get_settings().registration_system_options)
    return {"options": [{"id": item["id"], "text": item["text"]} for item in options]}


@router.get(f"{_DAILY_BASE}/api/status")
async def register_daily_status(token: str = Query(...)) -> dict[str, Any]:
    session = _resolve_session(token)
    return {
        "demand_content": session.demand_content,
        "system": session.system_name,
        "image_count": len(session.uploaded_images),
        "max_images": MAX_REGISTRATION_IMAGES,
        "images": [
            {
                "title": item.get("title", f"图片{index}"),
                "preview_url": (
                    f"{_DAILY_BASE}/api/preview?token={token}&index={index - 1}"
                ),
            }
            for index, item in enumerate(session.uploaded_images, start=1)
        ],
    }


@router.get(f"{_DAILY_BASE}/api/jssdk-config")
async def register_daily_jssdk_config(
    token: str = Query(...),
    url: str = Query(...),
) -> dict[str, Any]:
    _resolve_session(token)
    return build_jssdk_config(url)


@router.get(f"{_DAILY_BASE}/api/preview")
async def register_daily_preview(
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


@router.post(f"{_DAILY_BASE}/api/image")
async def register_daily_upload_image(
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

    return JSONResponse(
        {
            "ok": True,
            "image_count": len(session.uploaded_images),
            "max_images": MAX_REGISTRATION_IMAGES,
        }
    )


@router.post(f"{_DAILY_BASE}/api/image/delete")
async def register_daily_delete_image(
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


@router.post(f"{_DAILY_BASE}/api/submit")
async def register_daily_submit(
    request: Request,
    body: DailyRegisterSubmitBody,
    token: str = Query(...),
) -> JSONResponse:
    session = _resolve_session(token)
    demand_content = body.demand_content.strip()
    system = body.system.strip()

    options = parse_option_list(get_settings().registration_system_options)
    valid_systems = {item["text"] for item in options}
    if valid_systems and system not in valid_systems:
        raise HTTPException(status_code=400, detail="所属系统无效")

    session.demand_content = demand_content
    session.system_name = system

    images = registration_store.list_smartsheet_images(session.task_id)
    ok, errmsg = add_demand_record(
        demand_content,
        userid=session.userid,
        system=system,
        images=images or None,
    )
    if not ok:
        raise HTTPException(status_code=502, detail=errmsg or "写入智能表格失败")

    logger.info(
        "登记 H5 提交成功 userid=%s system=%s image_count=%s",
        session.userid,
        system,
        len(images),
    )
    registration_store.clear(session.task_id, session.userid)
    await _notify_register_success(request, session.userid)
    return JSONResponse({"ok": True})
