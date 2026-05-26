"""上线测试 H5 评价路由。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from app.config import get_settings
from app.feedback_token import create_feedback_token, verify_feedback_token
from app.smartsheet_reader import fetch_record_by_id
from app.smartsheet_writer import update_demand_feedback
from app.wecom_jssdk import build_jssdk_config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["feedback"])

_HTML_PATH = Path(__file__).resolve().parent.parent / "static" / "feedback.html"


def build_feedback_page_url(record_id: str, userid: str) -> str:
    settings = get_settings()
    base = settings.public_base_url.rstrip("/")
    if not base:
        return ""
    token = create_feedback_token(record_id, userid)
    path = settings.feedback_path.rstrip("/")
    return f"{base}{path}?token={token}"


class FeedbackSubmitBody(BaseModel):
    test_result: str = Field(..., min_length=1, max_length=32)
    satisfaction_score: int = Field(..., ge=1, le=10)


def _resolve_token(token: str) -> tuple[str, str]:
    parsed = verify_feedback_token(token)
    if parsed is None:
        raise HTTPException(status_code=403, detail="链接无效或已过期，请重新打开提醒卡片")
    return parsed


def _load_record(record_id: str, userid: str):
    try:
        record = fetch_record_by_id(record_id)
    except RuntimeError as exc:
        logger.exception("拉取评价记录失败 record_id=%s", record_id)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if record is None:
        raise HTTPException(status_code=404, detail="需求记录不存在")
    if record.submitter_userid != userid:
        raise HTTPException(status_code=403, detail="无权评价该需求")
    return record


def _record_to_detail(record) -> dict[str, Any]:
    settings = get_settings()
    pass_value = settings.launch_test_pass_value.strip()
    already_submitted = bool(pass_value and record.test_result_text == pass_value)
    return {
        "demand_content": record.demand_content,
        "system_name": record.system_name,
        "progress_text": record.progress_text,
        "test_result_text": record.test_result_text,
        "satisfaction_text": record.satisfaction_text,
        "already_submitted": already_submitted,
        "test_pass_value": settings.launch_test_pass_value,
        "test_fail_value": settings.feedback_test_fail_value,
    }


@router.get("/feedback", response_class=HTMLResponse)
async def feedback_page(token: str = Query(...)) -> HTMLResponse:
    _resolve_token(token)
    if not _HTML_PATH.is_file():
        raise HTTPException(status_code=500, detail="评价页面缺失")
    return HTMLResponse(_HTML_PATH.read_text(encoding="utf-8"))


@router.get("/feedback/api/detail")
async def feedback_detail(token: str = Query(...)) -> dict[str, Any]:
    record_id, userid = _resolve_token(token)
    record = _load_record(record_id, userid)
    return _record_to_detail(record)


@router.get("/feedback/api/jssdk-config")
async def feedback_jssdk_config(
    token: str = Query(...),
    url: str = Query(...),
) -> dict[str, Any]:
    _resolve_token(token)
    return build_jssdk_config(url)


@router.post("/feedback/api/submit")
async def feedback_submit(
    body: FeedbackSubmitBody,
    token: str = Query(...),
) -> JSONResponse:
    settings = get_settings()
    record_id, userid = _resolve_token(token)
    record = _load_record(record_id, userid)

    pass_value = settings.launch_test_pass_value.strip()
    if pass_value and record.test_result_text == pass_value:
        raise HTTPException(status_code=400, detail="该需求已评价，无需重复提交")

    allowed = {
        settings.launch_test_pass_value.strip(),
        settings.feedback_test_fail_value.strip(),
    }
    if body.test_result not in allowed:
        raise HTTPException(status_code=400, detail="测试结果无效")

    ok, errmsg = update_demand_feedback(
        record_id,
        test_result=body.test_result,
        satisfaction_score=body.satisfaction_score,
    )
    if not ok:
        raise HTTPException(status_code=502, detail=errmsg or "写入智能表格失败")

    logger.info(
        "H5 评价提交成功 record_id=%s userid=%s result=%s score=%s",
        record_id,
        userid,
        body.test_result,
        body.satisfaction_score,
    )
    return JSONResponse({"ok": True})
