"""企业微信自建应用 access_token 缓存。"""

from __future__ import annotations

import logging
import time
from threading import Lock

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_QYAPI = "https://qyapi.weixin.qq.com/cgi-bin"


class CorpAccessTokenProvider:
    def __init__(self, corp_id: str, corp_secret: str) -> None:
        self._corp_id = corp_id
        self._corp_secret = corp_secret
        self._lock = Lock()
        self._access_token = ""
        self._access_token_expires = 0.0

    def get_access_token(self) -> str:
        now = time.time()
        with self._lock:
            if self._access_token and now < self._access_token_expires - 120:
                return self._access_token

            response = httpx.get(
                f"{_QYAPI}/gettoken",
                params={"corpid": self._corp_id, "corpsecret": self._corp_secret},
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
            if data.get("errcode", 0) != 0:
                raise RuntimeError(
                    f"gettoken errcode={data.get('errcode')} errmsg={data.get('errmsg')}"
                )

            self._access_token = str(data["access_token"])
            self._access_token_expires = now + float(data.get("expires_in", 7200))
            logger.debug("已刷新 corp access_token")
            return self._access_token


_provider: CorpAccessTokenProvider | None = None


def get_corp_access_token_provider() -> CorpAccessTokenProvider | None:
    global _provider
    settings = get_settings()
    if not settings.wecom_corp_id or not settings.wecom_corp_secret:
        return None
    if _provider is None:
        _provider = CorpAccessTokenProvider(
            settings.wecom_corp_id,
            settings.wecom_corp_secret,
        )
    return _provider
