"""企业微信 JS-SDK 签名（H5 closeWindow 等）。"""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
from threading import Lock

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_QYAPI = "https://qyapi.weixin.qq.com/cgi-bin"


class WeComJssdkSigner:
    def __init__(self, corp_id: str, corp_secret: str) -> None:
        self.corp_id = corp_id
        self.corp_secret = corp_secret
        self._lock = Lock()
        self._access_token = ""
        self._access_token_expires = 0.0
        self._jsapi_ticket = ""
        self._jsapi_ticket_expires = 0.0
        self._agent_ticket = ""
        self._agent_ticket_expires = 0.0

    def _get_access_token(self) -> str:
        now = time.time()
        if self._access_token and now < self._access_token_expires - 120:
            return self._access_token

        response = httpx.get(
            f"{_QYAPI}/gettoken",
            params={"corpid": self.corp_id, "corpsecret": self.corp_secret},
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("errcode", 0) != 0:
            raise RuntimeError(f"gettoken errcode={data.get('errcode')} errmsg={data.get('errmsg')}")

        self._access_token = str(data["access_token"])
        self._access_token_expires = now + float(data.get("expires_in", 7200))
        return self._access_token

    def _get_jsapi_ticket(self) -> str:
        now = time.time()
        if self._jsapi_ticket and now < self._jsapi_ticket_expires - 120:
            return self._jsapi_ticket

        response = httpx.get(
            f"{_QYAPI}/get_jsapi_ticket",
            params={"access_token": self._get_access_token()},
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("errcode", 0) != 0:
            raise RuntimeError(
                f"get_jsapi_ticket errcode={data.get('errcode')} errmsg={data.get('errmsg')}"
            )

        self._jsapi_ticket = str(data["ticket"])
        self._jsapi_ticket_expires = now + float(data.get("expires_in", 7200))
        return self._jsapi_ticket

    def _get_agent_ticket(self) -> str:
        now = time.time()
        if self._agent_ticket and now < self._agent_ticket_expires - 120:
            return self._agent_ticket

        response = httpx.get(
            f"{_QYAPI}/ticket/get",
            params={"access_token": self._get_access_token(), "type": "agent_config"},
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("errcode", 0) != 0:
            raise RuntimeError(
                f"ticket/get agent_config errcode={data.get('errcode')} errmsg={data.get('errmsg')}"
            )

        self._agent_ticket = str(data["ticket"])
        self._agent_ticket_expires = now + float(data.get("expires_in", 7200))
        return self._agent_ticket

    @staticmethod
    def normalize_url(url: str) -> str:
        return url.split("#", 1)[0]

    @staticmethod
    def _build_signature(ticket: str, url: str) -> dict[str, int | str]:
        nonce_str = secrets.token_hex(8)
        timestamp = int(time.time())
        plain = (
            f"jsapi_ticket={ticket}&noncestr={nonce_str}"
            f"&timestamp={timestamp}&url={url}"
        )
        signature = hashlib.sha1(plain.encode()).hexdigest()
        return {
            "timestamp": timestamp,
            "nonceStr": nonce_str,
            "signature": signature,
        }

    def create_config_signature(self, url: str) -> dict[str, int | str]:
        with self._lock:
            ticket = self._get_jsapi_ticket()
            return self._build_signature(ticket, self.normalize_url(url))

    def create_agent_config_signature(self, url: str) -> dict[str, int | str]:
        with self._lock:
            ticket = self._get_agent_ticket()
            return self._build_signature(ticket, self.normalize_url(url))


_signer: WeComJssdkSigner | None = None


def get_jssdk_signer() -> WeComJssdkSigner | None:
    global _signer
    settings = get_settings()
    if not settings.wecom_corp_id or not settings.wecom_corp_secret:
        return None
    if _signer is None:
        _signer = WeComJssdkSigner(settings.wecom_corp_id, settings.wecom_corp_secret)
    return _signer


def build_jssdk_config(page_url: str) -> dict[str, object]:
    settings = get_settings()
    signer = get_jssdk_signer()
    if signer is None:
        return {"enabled": False}

    try:
        config = signer.create_config_signature(page_url)
        payload: dict[str, object] = {
            "enabled": True,
            "corpId": settings.wecom_corp_id,
            "config": config,
        }
        if settings.wecom_agent_id:
            payload["agentId"] = int(settings.wecom_agent_id)
            payload["agentConfig"] = signer.create_agent_config_signature(page_url)
        return payload
    except Exception as exc:
        logger.warning("生成 JS-SDK 签名失败: %s", exc)
        return {"enabled": False, "error": str(exc)}
