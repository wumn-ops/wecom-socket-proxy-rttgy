"""WebSocket 长连接生命周期管理。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from wecom_aibot_sdk import WSClient

from app import connection_state
from app.config import Settings
from app.launch_notifier import LaunchNotifierService
from app.message_handler import BotMessageHandler

logger = logging.getLogger(__name__)


class WebSocketBotService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: WSClient | None = None
        self._handler: BotMessageHandler | None = None
        self._task: asyncio.Task[None] | None = None
        self._launch_notifier = LaunchNotifierService(settings, lambda: self._client)

    @property
    def client(self) -> WSClient | None:
        return self._client

    @property
    def handler(self) -> BotMessageHandler | None:
        return self._handler

    async def start(self) -> None:
        if not self._settings.wecom_bot_id or not self._settings.wecom_bot_secret:
            logger.error("未配置 WECOM_BOT_ID / WECOM_BOT_SECRET，跳过 WebSocket 连接")
            connection_state.state.last_error = "missing bot credentials"
            connection_state.state.touch()
            return

        self._client = WSClient(
            bot_id=self._settings.wecom_bot_id,
            secret=self._settings.wecom_bot_secret,
            max_reconnect_attempts=-1,
        )
        self._handler = BotMessageHandler(self._client)
        self._register_events()
        self._task = asyncio.create_task(self._run_forever(), name="wecom-ws-client")
        await self._launch_notifier.start()

    async def stop(self) -> None:
        await self._launch_notifier.stop()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._client is not None:
            await self._client.disconnect()
            self._client = None
        connection_state.state.connected = False
        connection_state.state.authenticated = False
        connection_state.state.touch()

    async def _run_forever(self) -> None:
        assert self._client is not None
        while True:
            try:
                await self._client.connect()
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                connection_state.state.last_error = str(exc)
                connection_state.state.touch()
                logger.exception("WebSocket 运行异常，5 秒后重试: %s", exc)
                await asyncio.sleep(5)

    def _register_events(self) -> None:
        assert self._client is not None
        assert self._handler is not None
        client = self._client
        handler = self._handler

        def on_connected() -> None:
            connection_state.state.connected = True
            connection_state.state.touch()
            logger.info("WebSocket 已连接")

        def on_authenticated() -> None:
            connection_state.state.authenticated = True
            connection_state.state.reconnect_attempt = 0
            connection_state.state.last_error = ""
            connection_state.state.touch()
            logger.info("WebSocket 认证成功")

        def on_disconnected(reason: str) -> None:
            connection_state.state.connected = False
            connection_state.state.authenticated = False
            connection_state.state.touch()
            logger.warning("WebSocket 已断开: %s", reason)

        def on_reconnecting(attempt: int) -> None:
            connection_state.state.reconnect_attempt = attempt
            connection_state.state.touch()
            logger.info("WebSocket 重连中 attempt=%s", attempt)

        def on_error(error: Exception) -> None:
            connection_state.state.last_error = str(error)
            connection_state.state.touch()
            logger.error("WebSocket 错误: %s", error)

        async def on_enter(frame: dict[str, Any]) -> None:
            await handler.on_enter_chat(frame)

        async def on_card(frame: dict[str, Any]) -> None:
            await handler.on_template_card_event(frame)

        async def on_text(frame: dict[str, Any]) -> None:
            await handler.on_text(frame)

        async def on_image(frame: dict[str, Any]) -> None:
            await handler.on_image(frame)

        client.on("connected", on_connected)
        client.on("authenticated", on_authenticated)
        client.on("disconnected", on_disconnected)
        client.on("reconnecting", on_reconnecting)
        client.on("error", on_error)
        client.on("event.enter_chat", on_enter)
        client.on("event.template_card_event", on_card)
        client.on("message.text", on_text)
        client.on("message.image", on_image)
