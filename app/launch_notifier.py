"""定时扫描智能表格「已上线」记录并主动提醒需求提出人测试。"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from wecom_aibot_sdk import WSClient

from app import connection_state
from app.config import Settings
from app.notified_store import NotifiedRecordStore
from app.feedback_routes import build_feedback_page_url
from app.smartsheet_reader import SmartsheetRecord, fetch_launched_records
from app.template_cards import build_launch_test_reminder_card

logger = logging.getLogger(__name__)

_ACK_TIMEOUT_MARK = "Reply ack timeout"


def _is_late_ack_timeout(exc: Exception) -> bool:
    """SDK 等待回执超时，但企微侧可能已成功投递（errcode=0 晚到会被 SDK 丢弃）。"""
    return _ACK_TIMEOUT_MARK in str(exc)


class LaunchNotifierService:
    def __init__(self, settings: Settings, client_getter) -> None:
        self._settings = settings
        self._client_getter = client_getter
        self._task: asyncio.Task[None] | None = None
        self._store = NotifiedRecordStore(Path(settings.launch_notify_state_path))

    @property
    def enabled(self) -> bool:
        return bool(
            self._settings.launch_notify_enabled
            and self._settings.smartsheet_docid
            and self._settings.smartsheet_sheet_id
            and self._settings.wecom_corp_id
            and self._settings.wecom_corp_secret
        )

    async def start(self) -> None:
        if not self.enabled:
            logger.info("上线测试提醒未启用或配置不完整，跳过定时任务")
            return
        self._task = asyncio.create_task(self._run_loop(), name="launch-notifier")
        logger.info(
            "上线测试提醒已启动 interval=%ss state=%s",
            self._settings.launch_poll_interval_seconds,
            self._settings.launch_notify_state_path,
        )

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run_loop(self) -> None:
        interval = max(10, self._settings.launch_poll_interval_seconds)
        while True:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("上线测试提醒轮询失败")
            await asyncio.sleep(interval)

    async def _poll_once(self) -> None:
        if not connection_state.state.authenticated:
            logger.debug("WebSocket 未认证，跳过本轮上线提醒扫描")
            return

        client: WSClient | None = self._client_getter()
        if client is None:
            logger.debug("WebSocket 客户端不可用，跳过本轮上线提醒扫描")
            return

        records = await asyncio.to_thread(fetch_launched_records)
        if not records:
            logger.debug("本轮未发现进度为「%s」的记录", self._settings.launch_progress_value)
            return

        sent_count = 0
        for record in records:
            if self._store.contains(record.record_id):
                continue
            ok = await self._notify_user(client, record)
            if ok:
                self._store.add(record.record_id)
                sent_count += 1

        if sent_count:
            logger.info("本轮发送上线测试提醒 %s 条", sent_count)

    async def _notify_user(self, client: WSClient, record: SmartsheetRecord) -> bool:
        card = build_launch_test_reminder_card(
            demand_content=record.demand_content,
            system_name=record.system_name,
            feedback_url=build_feedback_page_url(record.record_id, record.submitter_userid),
        )
        try:
            await client.send_message(
                record.submitter_userid,
                {
                    "msgtype": "template_card",
                    "template_card": card,
                },
            )
        except Exception as exc:
            if _is_late_ack_timeout(exc):
                logger.warning(
                    "发送上线测试提醒 ack 超时（消息可能已送达）record_id=%s userid=%s",
                    record.record_id,
                    record.submitter_userid,
                )
                return True
            logger.exception(
                "发送上线测试提醒失败 record_id=%s userid=%s",
                record.record_id,
                record.submitter_userid,
            )
            return False

        logger.info(
            "已发送上线测试提醒 record_id=%s userid=%s",
            record.record_id,
            record.submitter_userid,
        )
        return True
