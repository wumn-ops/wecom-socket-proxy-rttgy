"""智能表格「接收外部数据」Webhook 客户端（101239）。"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


def add_demand_record(
    content: str,
    *,
    userid: str | None = None,
    system: str | None = None,
    images: list[dict[str, str]] | None = None,
) -> tuple[bool, str]:
    """向智能表格新增一条记录，写入需求内容、提出人、所属系统与可选图片。"""
    settings = get_settings()
    if not settings.smartsheet_webhook_url:
        return False, "未配置 SMARTSHEET_WEBHOOK_URL"

    content_field = settings.smartsheet_field_demand_content
    values: dict[str, Any] = {content_field: content}

    if userid:
        submitter_field = settings.smartsheet_field_submitter
        values[submitter_field] = [{"user_id": userid}]

    if system:
        system_field = settings.smartsheet_field_system
        values[system_field] = system

    if images:
        image_field = settings.smartsheet_field_image
        values[image_field] = [
            {
                "title": item.get("title") or f"图片{index}",
                "image_base64": item["image_base64"],
            }
            for index, item in enumerate(images, start=1)
        ]

    payload: dict[str, Any] = {
        "add_records": [
            {
                "values": values,
            }
        ]
    }

    try:
        response = httpx.post(
            settings.smartsheet_webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as exc:
        logger.exception("智能表格 Webhook 请求失败")
        return False, f"网络请求失败: {exc}"
    except ValueError as exc:
        logger.exception("智能表格 Webhook 响应解析失败")
        return False, f"响应解析失败: {exc}"

    errcode = data.get("errcode")
    if errcode == 0:
        logger.info(
            "智能表格写入成功 content_field=%s submitter=%s system=%s image_count=%s",
            content_field,
            userid or "",
            system or "",
            len(images or []),
        )
        return True, "ok"

    errmsg = data.get("errmsg", "未知错误")
    logger.error("智能表格写入失败 errcode=%s errmsg=%s", errcode, errmsg)
    return False, str(errmsg)
