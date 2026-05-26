"""H5 上传页访问令牌。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from app.config import get_settings


def create_upload_token(task_id: str, userid: str) -> str:
    settings = get_settings()
    exp = int(time.time()) + settings.upload_token_ttl_seconds
    payload = json.dumps(
        {"t": task_id, "u": userid, "e": exp},
        separators=(",", ":"),
        ensure_ascii=False,
    )
    sig = _sign(payload)
    token_raw = f"{payload}.{sig}"
    return base64.urlsafe_b64encode(token_raw.encode("utf-8")).decode("ascii").rstrip("=")


def verify_upload_token(token: str) -> tuple[str, str] | None:
    if not token:
        return None

    padded = token + "=" * (-len(token) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None

    payload, _, sig = decoded.rpartition(".")
    if not payload or not sig or not hmac.compare_digest(_sign(payload), sig):
        return None

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None

    task_id = data.get("t")
    userid = data.get("u")
    exp = data.get("e")
    if not isinstance(task_id, str) or not isinstance(userid, str) or not isinstance(exp, int):
        return None
    if exp < int(time.time()):
        return None
    return task_id, userid


def _sign(payload: str) -> str:
    settings = get_settings()
    secret = (
        settings.upload_token_secret
        or settings.wecom_bot_secret
        or "wecom-socket-proxy-fkh-upload"
    )
    return hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]
