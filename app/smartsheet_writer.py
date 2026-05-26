"""智能表格更新记录（update_records，101168）。"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.config import get_settings
from app.wecom_token import get_corp_access_token_provider

logger = logging.getLogger(__name__)

_QYAPI_UPDATE = "https://qyapi.weixin.qq.com/cgi-bin/wedoc/smartsheet/update_records"


def _format_select_value(text: str) -> list[dict[str, str]]:
    """单选/下拉字段须为 [{\"text\": \"选项\"}]，与表格 Webhook 示例一致。"""
    return [{"text": text}]


def _format_score_value(score: int) -> list[dict[str, str]]:
    """满意度等文本型分数字段须为 [{\"text\": \"8\"}]。"""
    return [{"text": str(score)}]


def _build_feedback_values(test_result: str, satisfaction_score: int) -> dict[str, Any]:
    settings = get_settings()
    return {
        settings.smartsheet_field_test_result: _format_select_value(test_result),
        settings.smartsheet_field_satisfaction: _format_score_value(satisfaction_score),
    }


def update_demand_feedback(
    record_id: str,
    *,
    test_result: str,
    satisfaction_score: int,
) -> tuple[bool, str]:
    """回写测试结果与满意度打分。"""
    settings = get_settings()
    if not settings.smartsheet_docid or not settings.smartsheet_sheet_id:
        return False, "未配置 SMARTSHEET_DOCID / SMARTSHEET_SHEET_ID"

    values: dict[str, Any] = _build_feedback_values(test_result, satisfaction_score)

    webhook_err = ""
    if settings.smartsheet_webhook_url:
        webhook_ok, webhook_err = _update_via_webhook(record_id, values)
        if webhook_ok:
            return _verify_feedback_written(record_id, test_result, satisfaction_score)

    ok, corp_err = _update_via_corp_api(record_id, values)
    if ok:
        return _verify_feedback_written(record_id, test_result, satisfaction_score)

    return False, corp_err or webhook_err or "写入智能表格失败"


def _update_via_corp_api(record_id: str, values: dict[str, Any]) -> tuple[bool, str]:
    settings = get_settings()
    provider = get_corp_access_token_provider()
    if provider is None:
        return False, "未配置 WECOM_CORP_ID / WECOM_CORP_SECRET"

    access_token = provider.get_access_token()
    payload = {
        "docid": settings.smartsheet_docid,
        "sheet_id": settings.smartsheet_sheet_id,
        "key_type": "CELL_VALUE_KEY_TYPE_FIELD_ID",
        "records": [
            {
                "record_id": record_id,
                "values": values,
            }
        ],
    }

    try:
        response = httpx.post(
            _QYAPI_UPDATE,
            params={"access_token": access_token},
            json=payload,
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as exc:
        logger.exception("智能表格 update_records 请求失败")
        return False, f"网络请求失败: {exc}"
    except ValueError as exc:
        logger.exception("智能表格 update_records 响应解析失败")
        return False, f"响应解析失败: {exc}"

    errcode = data.get("errcode")
    if errcode is None:
        logger.error("智能表格 update_records 响应缺少 errcode: %s", data)
        return False, "智能表格响应异常"
    if errcode == 0:
        logger.info(
            "智能表格 update_records 请求成功 record_id=%s response=%s",
            record_id,
            json.dumps(data, ensure_ascii=False)[:300],
        )
        return True, "ok"

    errmsg = data.get("errmsg", "未知错误")
    logger.error(
        "智能表格 update_records 失败 errcode=%s errmsg=%s record_id=%s",
        errcode,
        errmsg,
        record_id,
    )
    return False, str(errmsg)


def _update_via_webhook(record_id: str, values: dict[str, Any]) -> tuple[bool, str]:
    settings = get_settings()
    payload = {
        "update_records": [
            {
                "record_id": record_id,
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
        logger.exception("智能表格 Webhook update_records 请求失败")
        return False, f"网络请求失败: {exc}"
    except ValueError as exc:
        logger.exception("智能表格 Webhook update_records 响应解析失败")
        return False, f"响应解析失败: {exc}"

    errcode = data.get("errcode")
    if errcode is None:
        logger.error("智能表格 Webhook update_records 响应缺少 errcode: %s", data)
        return False, "智能表格响应异常"
    if errcode == 0:
        logger.info(
            "智能表格 Webhook update_records 请求成功 record_id=%s response=%s",
            record_id,
            json.dumps(data, ensure_ascii=False)[:300],
        )
        return True, "ok"

    errmsg = data.get("errmsg", "未知错误")
    logger.error(
        "智能表格 Webhook update_records 失败 errcode=%s errmsg=%s",
        errcode,
        errmsg,
    )
    return False, str(errmsg)


def _verify_feedback_written(
    record_id: str,
    test_result: str,
    satisfaction_score: int,
) -> tuple[bool, str]:
    """写后读回校验，避免 API errcode=0 但单元格未真正落库。"""
    from app.smartsheet_reader import fetch_record_by_id

    try:
        record = fetch_record_by_id(record_id)
    except Exception as exc:
        logger.exception("写后校验读表失败 record_id=%s", record_id)
        return False, f"写入后校验失败: {exc}"

    if record is None:
        return False, "写入后校验失败：记录不存在"

    expected_score = str(satisfaction_score)
    if record.test_result_text == test_result and record.satisfaction_text == expected_score:
        logger.info(
            "智能表格评价回写校验通过 record_id=%s result=%s score=%s",
            record_id,
            test_result,
            expected_score,
        )
        return True, "ok"

    logger.error(
        "智能表格评价回写校验未通过 record_id=%s expected=(%s,%s) actual=(%s,%s)",
        record_id,
        test_result,
        expected_score,
        record.test_result_text,
        record.satisfaction_text,
    )
    return False, "写入智能表格未生效，请稍后重试或联系管理员"
