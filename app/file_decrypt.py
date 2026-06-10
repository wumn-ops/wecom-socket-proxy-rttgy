"""公司加密文件解密（对接 vazyme-bc /api/jiemi/decrypt）。"""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import unquote

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_FILENAME_RE = re.compile(r"""filename\*?=(?:UTF-8''|"?)([^";]+)"?""", re.IGNORECASE)


def _parse_output_filename(content_disposition: str | None, fallback: str) -> str:
    if not content_disposition:
        return fallback
    match = _FILENAME_RE.search(content_disposition)
    if not match:
        return fallback
    try:
        return unquote(match.group(1).strip())
    except Exception:
        return fallback


def decrypt_encrypted_file(
    user_id: str,
    file_bytes: bytes,
    filename: str,
) -> tuple[bool, bytes | str, str]:
    """调用解密接口，返回 (成功, 解密字节或错误信息, 输出文件名)。"""
    settings = get_settings()
    api_url = settings.file_decrypt_api_url.strip()
    token = settings.file_decrypt_token.strip()
    if not api_url or not token:
        return False, "解密服务未配置", filename
    if not user_id.strip():
        return False, "缺少用户工号，无法解密", filename

    files = {"file": (filename or "upload.bin", file_bytes, "application/octet-stream")}
    data = {"userId": user_id.strip()}
    headers = {"vzSfsToken": token}

    try:
        response = httpx.post(
            api_url,
            data=data,
            files=files,
            headers=headers,
            timeout=60.0,
            verify=settings.file_decrypt_ssl_verify,
        )
    except httpx.HTTPError as exc:
        logger.warning("解密接口请求失败 user_id=%s filename=%s err=%s", user_id, filename, exc)
        return False, f"解密服务不可用: {exc}", filename

    content_type = (response.headers.get("content-type") or "").lower()
    body = response.content

    if "application/json" in content_type:
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False, "解密失败：响应格式异常", filename
        if not payload.get("success", True):
            message = payload.get("message") or payload.get("msg") or "解密失败"
            return False, str(message), filename
        if isinstance(payload.get("data"), str):
            return False, payload["data"], filename
        return False, "解密失败：未返回文件内容", filename

    if response.status_code >= 400:
        text = body.decode("utf-8", errors="replace")[:200]
        return False, text or f"解密失败(HTTP {response.status_code})", filename

    output_name = _parse_output_filename(
        response.headers.get("content-disposition"),
        filename,
    )
    if not body:
        return False, "解密失败：返回内容为空", filename

    logger.info(
        "文件解密成功 user_id=%s input=%s output=%s bytes=%s",
        user_id,
        filename,
        output_name,
        len(body),
    )
    return True, body, output_name
