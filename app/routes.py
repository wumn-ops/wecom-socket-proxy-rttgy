from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, Response

from app import connection_state
from app.config import get_settings
from app.ws_service import WebSocketBotService

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


def _bot_service(request: Request) -> WebSocketBotService:
    service = getattr(request.app.state, "bot_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="WebSocket 服务未初始化")
    return service


@router.get(settings.health_path)
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "mode": "websocket",
        "websocket": connection_state.state.snapshot(),
    }


@router.get(settings.wecom_callback_path)
async def callback_placeholder_get() -> dict[str, str]:
    """Webhook 占位：当前服务使用长连接，不处理 URL 验证。"""
    return {
        "service": "wecom-socket-proxy-rttgy",
        "mode": "websocket",
        "message": "本服务为长连接模式，消息经 WebSocket 收发；此路径仅保留给 Nginx 占位。",
    }


@router.post(settings.wecom_callback_path)
async def callback_placeholder_post(request: Request) -> Response:
    """Webhook 占位：避免 Nginx 转发到此路径时 404。"""
    body = await request.body()
    logger.info("收到 Webhook 占位 POST len=%s（长连接模式不处理）", len(body))
    return Response(content="", media_type="text/plain")


@router.post("/api/test/push")
async def test_proactive_push(
    request: Request,
    chat_id: str | None = None,
) -> dict[str, object]:
    """测试主动推送（需已有会话上下文或显式传 chat_id）。"""
    bot_service = _bot_service(request)
    if bot_service.handler is None:
        raise HTTPException(status_code=503, detail="WebSocket 未就绪")
    ok = await bot_service.handler.send_proactive_push(chat_id=chat_id)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="推送失败：请传 chat_id 或先与机器人发一条消息",
        )
    return {"ok": True, "chat_id": chat_id or connection_state.state.last_chat_id}
