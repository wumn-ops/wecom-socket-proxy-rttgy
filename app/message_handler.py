"""WebSocket 消息与事件处理。"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from wecom_aibot_sdk import WSClient, generate_req_id

from app import connection_state
from app.config import get_settings
from app.registrations import MAX_REGISTRATION_IMAGES, registration_store
from app.smartsheet import add_demand_record
from app.system_options import parse_option_list, parse_system_selection
from app.template_cards import (
    build_button_clicked_card,
    build_demo_action_card,
    build_push_notice_card,
    build_register_cancelled_card,
    build_register_confirm_card,
    build_register_failed_card,
    build_register_session_expired_card,
    build_register_success_card,
    build_welcome_card,
    new_task_id,
)
from app.upload_routes import build_upload_page_url

logger = logging.getLogger(__name__)

REGISTER_SUBMIT_KEY = "register_submit"
REGISTER_CANCEL_KEY = "register_cancel"

HELP_TEXT = (
    "可用指令：\n"
    "- 登记 需求内容：发起需求登记（需选择所属系统）\n"
    "- ping / 测试：流式 echo\n"
    "- /help：本帮助\n"
    "- 卡片 / /card：回复示例交互卡片\n"
    "- 主动推送 / /push：测试 aibot_send_msg\n"
    "- 其他文本：流式 echo 回复"
)


def _frame_body(frame: dict[str, Any]) -> dict[str, Any]:
    body = frame.get("body")
    return body if isinstance(body, dict) else {}


def _chat_target(body: dict[str, Any]) -> str:
    chatid = str(body.get("chatid") or "").strip()
    if chatid:
        return chatid
    from_info = body.get("from") or {}
    return str(from_info.get("userid") or "").strip()


def _userid(body: dict[str, Any]) -> str:
    from_info = body.get("from") or {}
    return str(from_info.get("userid") or "").strip()


def _chattype(body: dict[str, Any]) -> str:
    return str(body.get("chattype") or "single")


def _remember_context(body: dict[str, Any]) -> None:
    chat_id = _chat_target(body)
    userid = _userid(body)
    if chat_id:
        connection_state.state.last_chat_id = chat_id
    if userid:
        connection_state.state.last_userid = userid
    connection_state.state.touch()


def _template_card_event(body: dict[str, Any]) -> dict[str, Any]:
    event = body.get("event") or {}
    if not isinstance(event, dict):
        return {}
    card_event = event.get("template_card_event") or {}
    return card_event if isinstance(card_event, dict) else {}


def _parse_registration_text(text: str) -> tuple[bool, str]:
    idx = text.find("登记")
    if idx == -1:
        return False, ""
    content = text[idx + len("登记") :].strip()
    content = re.sub(r"^[：:\-,，\s]+", "", content)
    return True, content


class BotMessageHandler:
    def __init__(self, client: WSClient) -> None:
        self._client = client

    async def on_enter_chat(self, frame: dict[str, Any]) -> None:
        body = _frame_body(frame)
        _remember_context(body)
        logger.info("进入会话 chat=%s user=%s", _chat_target(body), _userid(body))
        await self._client.reply_welcome(
            frame,
            {
                "msgtype": "template_card",
                "template_card": build_welcome_card(),
            },
        )

    async def on_template_card_event(self, frame: dict[str, Any]) -> None:
        body = _frame_body(frame)
        _remember_context(body)
        card_event = _template_card_event(body)
        card_type = str(card_event.get("card_type") or "")
        if card_type and card_type != "button_interaction":
            logger.info("暂不支持更新的卡片类型: %s", card_type)
            return

        event_key = str(card_event.get("event_key") or "")
        task_id = str(card_event.get("task_id") or "")
        if not task_id:
            logger.warning("模板卡片事件缺少 task_id: %s", card_event)
            return

        logger.info("模板卡片点击 event_key=%s task_id=%s", event_key, task_id)

        registration = registration_store.get(task_id)
        if registration is None and _userid(body):
            pending = registration_store.get_pending(_userid(body))
            if pending is not None and pending.task_id == task_id:
                registration = pending

        if registration is not None:
            self._apply_registration_selection(registration, card_event)
            updated = await self._handle_registration_card_event(
                event_key=event_key,
                registration=registration,
                card_task_id=task_id,
            )
            await self._client.update_template_card(frame, updated)
            return

        if event_key in (REGISTER_SUBMIT_KEY, REGISTER_CANCEL_KEY):
            logger.info(
                "登记卡片事件无会话 task_id=%s event_key=%s",
                task_id,
                event_key,
            )
            await self._client.update_template_card(
                frame,
                build_register_session_expired_card(task_id=task_id),
            )
            return

        updated = build_button_clicked_card(event_key=event_key, task_id=task_id)
        await self._client.update_template_card(frame, updated)

    async def on_text(self, frame: dict[str, Any]) -> None:
        body = _frame_body(frame)
        _remember_context(body)
        text_obj = body.get("text") or {}
        content = str(text_obj.get("content") or "").strip()
        userid = _userid(body)
        logger.info("收到文本 user=%s content=%s", userid, content[:120])

        is_register, demand_content = _parse_registration_text(content)
        if is_register:
            await self._handle_registration_message(
                frame,
                demand_content=demand_content,
                userid=userid,
                chattype=_chattype(body),
            )
            return

        normalized = content.lower()
        if normalized in {"ping", "测试", "test"}:
            await self._reply_echo(frame, f"pong · 用户 `{userid}` · 长连接正常")
            return
        if normalized.startswith("/help") or content == "帮助":
            await self._reply_echo(frame, HELP_TEXT)
            return
        if normalized in {"/card", "卡片"}:
            await self._client.reply_template_card(
                frame,
                build_demo_action_card(user_text=content, userid=userid),
            )
            return
        if normalized in {"/push", "主动推送"}:
            await self._send_proactive_push()
            await self._reply_echo(frame, "已发送主动推送消息，请查看会话。")
            return

        await self._reply_echo(frame, f"echo: {content or '（空）'}")

    async def on_image(self, frame: dict[str, Any]) -> None:
        body = _frame_body(frame)
        _remember_context(body)
        await self._reply_registration_upload_hint(frame)

    async def _handle_registration_message(
        self,
        frame: dict[str, Any],
        *,
        demand_content: str,
        userid: str,
        chattype: str,
    ) -> None:
        if not demand_content:
            await self._reply_echo(
                frame,
                "请在「登记」后附上需求内容，例如：\n\n"
                "登记 希望优化报表导出速度\n\n"
                "发送确认卡片后，请选择所属系统，点「上传图片」附加截图（最多 3 张），"
                "完成后返回卡片点击「提交登记」。",
            )
            return

        task_id = new_task_id()
        registration_store.create(
            task_id=task_id,
            demand_content=demand_content,
            userid=userid,
            chattype=chattype,
        )
        upload_url = build_upload_page_url(task_id, userid)
        logger.info("创建登记会话 task_id=%s userid=%s", task_id, userid)

        if not upload_url:
            await self._reply_echo(
                frame,
                "登记会话已创建，但未配置 PUBLIC_BASE_URL，无法打开 H5 上传页。\n"
                "请在 .env 中设置 PUBLIC_BASE_URL 后重试。",
            )
            registration_store.clear(task_id, userid)
            return

        await self._client.reply_template_card(
            frame,
            build_register_confirm_card(
                demand_content=demand_content,
                userid=userid,
                task_id=task_id,
                upload_url=upload_url,
            ),
        )

    def _apply_registration_selection(
        self,
        registration,
        card_event: dict[str, Any],
    ) -> None:
        selected_items = (card_event.get("selected_items") or {}).get("selected_item")
        options = parse_option_list(get_settings().registration_system_options)
        selection = parse_system_selection(selected_items, options=options)
        if selection is None:
            return
        option_id, system_name = selection
        registration_store.update_system(
            registration.task_id,
            option_id=option_id,
            system_name=system_name,
        )
        registration.system_option_id = option_id
        registration.system_name = system_name

    async def _handle_registration_card_event(
        self,
        *,
        event_key: str,
        registration,
        card_task_id: str,
    ) -> dict[str, Any]:
        primary_task_id = registration.task_id
        content = registration.demand_content
        image_count = len(registration.uploaded_images)

        if event_key == REGISTER_CANCEL_KEY:
            registration_store.clear(primary_task_id, registration.userid)
            return build_register_cancelled_card(task_id=card_task_id)

        if event_key != REGISTER_SUBMIT_KEY:
            return self._build_registration_confirm_card(
                registration,
                task_id=card_task_id,
            )

        images = registration_store.list_smartsheet_images(primary_task_id)
        ok, errmsg = add_demand_record(
            content,
            userid=registration.userid,
            system=registration.system_name or None,
            images=images or None,
        )
        registration_store.clear(primary_task_id, registration.userid)

        if ok:
            return build_register_success_card(
                task_id=card_task_id,
                demand_content=content,
                image_count=image_count,
                system_name=registration.system_name,
            )
        return build_register_failed_card(task_id=card_task_id, error=errmsg)

    def _build_registration_confirm_card(self, registration, *, task_id: str) -> dict[str, Any]:
        return build_register_confirm_card(
            demand_content=registration.demand_content,
            userid=registration.userid,
            task_id=task_id,
            image_count=len(registration.uploaded_images),
            upload_url=build_upload_page_url(registration.task_id, registration.userid),
            system_option_id=registration.system_option_id,
        )

    async def _reply_registration_upload_hint(self, frame: dict[str, Any]) -> None:
        await self._reply_echo(
            frame,
            "请点击登记确认卡片中的「上传图片」附加截图（最多 "
            f"{MAX_REGISTRATION_IMAGES} 张），完成后返回卡片点击「提交登记」。",
        )

    async def _reply_echo(self, frame: dict[str, Any], content: str) -> None:
        stream_id = generate_req_id("stream")
        await self._client.reply_stream(frame, stream_id, "处理中…", False)
        await asyncio.sleep(0.3)
        await self._client.reply_stream(frame, stream_id, content, True)

    async def send_proactive_push(self, chat_id: str | None = None) -> bool:
        target = (chat_id or connection_state.state.last_chat_id).strip()
        if not target:
            logger.warning("主动推送失败：无可用 chat_id")
            return False
        await self._client.send_message(
            target,
            {
                "msgtype": "template_card",
                "template_card": build_push_notice_card(),
            },
        )
        logger.info("主动推送成功 chat=%s", target)
        return True

    async def _send_proactive_push(self) -> None:
        ok = await self.send_proactive_push()
        if not ok:
            raise RuntimeError("无会话上下文，请先与机器人发一条消息")
