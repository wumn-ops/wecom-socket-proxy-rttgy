"""企业微信模板卡片构建（101032，长连接模式示例）。"""

from __future__ import annotations

import re
import uuid
from typing import Any

from app.config import get_settings
from app.system_options import build_button_selection, parse_option_list


def new_task_id() -> str:
    return re.sub(r"[^0-9A-Za-z_\-@]", "", uuid.uuid4().hex)


def build_button_interaction_card(
    *,
    title: str,
    desc: str = "",
    sub_title: str = "",
    task_id: str | None = None,
    horizontal_items: list[dict[str, Any]] | None = None,
    buttons: list[dict[str, Any]] | None = None,
    button_selection: dict[str, Any] | None = None,
    source_desc: str = "wecom-socket-proxy-rttgy",
) -> dict[str, Any]:
    card: dict[str, Any] = {
        "card_type": "button_interaction",
        "source": {
            "icon_url": "https://wework.qpic.cn/wwpic/252813_jOfDHtcISzuodLa_1629280209/0",
            "desc": source_desc,
            "desc_color": 0,
        },
        "main_title": {
            "title": title[:26],
            "desc": desc[:30] if desc else "",
        },
        "button_list": buttons
        or [
            {"text": "确认", "style": 1, "key": "confirm"},
            {"text": "取消", "style": 2, "key": "cancel"},
        ],
        "task_id": task_id or new_task_id(),
    }
    if sub_title:
        card["sub_title_text"] = sub_title[:112]
    if horizontal_items:
        card["horizontal_content_list"] = horizontal_items[:6]
    if button_selection:
        card["button_selection"] = button_selection
    return card


def build_welcome_card(*, task_id: str | None = None, register_url: str = "") -> dict[str, Any]:
    start_button: dict[str, Any] = {"text": "开始登记", "style": 1, "key": "start"}
    if register_url:
        start_button = {
            "text": "开始登记",
            "style": 4,
            "type": 1,
            "url": register_url,
        }

    return build_button_interaction_card(
        title="欢迎使用需求登记助手",
        desc="如遇页面超时，发送任意消息呼出新卡片",
        sub_title="点击按钮填写需求并提交到智能表格",
        task_id=task_id or new_task_id(),
        horizontal_items=[
            {"keyname": "模式", "value": "长连接"},
            {"keyname": "说明", "value": "填写后自动写入表格"},
        ],
        buttons=[start_button],
        source_desc="需求登记助手",
    )


def build_demo_action_card(*, user_text: str, userid: str) -> dict[str, Any]:
    preview = user_text.strip()[:80] or "（空）"
    return build_button_interaction_card(
        title="示例交互卡片",
        desc="点击按钮可更新卡片",
        sub_title=f"您的输入：{preview}",
        task_id=new_task_id(),
        horizontal_items=[
            {"keyname": "用户", "value": userid[:26]},
            {"keyname": "提示", "value": "长连接 WS 测试"},
        ],
        buttons=[
            {"text": "确认", "style": 1, "key": "confirm"},
            {"text": "取消", "style": 2, "key": "cancel"},
        ],
    )


def build_button_clicked_card(*, event_key: str, task_id: str) -> dict[str, Any]:
    labels = {
        "confirm": "确认",
        "cancel": "取消",
        "demo_card": "示例卡片",
        "intro": "功能介绍",
        "start": "开始咨询",
    }
    action = labels.get(event_key, event_key or "未知")
    return build_button_interaction_card(
        title="操作已收到",
        desc="长连接卡片已更新",
        sub_title=f"您点击了：{action}",
        task_id=task_id,
        horizontal_items=[
            {"keyname": "操作", "value": action[:26]},
            {"keyname": "状态", "value": "已处理"},
        ],
        buttons=[
            {"text": "已完成", "style": 4, "key": "done"},
        ],
    )


def build_push_notice_card(*, title: str = "主动推送测试") -> dict[str, Any]:
    return build_button_interaction_card(
        title=title[:26],
        desc="aibot_send_msg",
        sub_title="这是一条主动推送的模板卡片",
        task_id=new_task_id(),
        horizontal_items=[
            {"keyname": "来源", "value": "长连接主动推送"},
        ],
        buttons=[
            {"text": "知道了", "style": 4, "key": "push_ack"},
        ],
    )


def build_register_confirm_card(
    *,
    demand_content: str,
    userid: str,
    task_id: str | None = None,
    image_count: int = 0,
    upload_url: str = "",
    max_images: int = 3,
    system_option_id: str = "",
) -> dict[str, Any]:
    preview = demand_content[:80] + ("…" if len(demand_content) > 80 else "")
    image_desc = (
        f"已上传 {image_count}/{max_images} 张"
        if image_count
        else f"可选，最多 {max_images} 张"
    )
    system_options = parse_option_list(get_settings().registration_system_options)
    selected_system_id = system_option_id or (
        system_options[0]["id"] if system_options else ""
    )
    system_label = next(
        (item["text"] for item in system_options if item["id"] == selected_system_id),
        "",
    )

    horizontal: list[dict[str, Any]] = [
        {"keyname": "提交人", "value": userid[:26]},
        {"keyname": "内容长度", "value": str(len(demand_content))},
        {"keyname": "图片", "value": image_desc[:26]},
    ]
    if system_label:
        horizontal.insert(1, {"keyname": "所属系统", "value": system_label[:26]})

    upload_button: dict[str, Any] = {"text": "上传图片", "style": 4, "key": "register_upload"}
    if upload_url:
        upload_button = {
            "text": "上传图片",
            "style": 4,
            "type": 1,
            "url": upload_url,
        }

    issue_list_url = get_settings().issue_list_url.strip()
    if issue_list_url:
        # 4 个按钮时客户端按 2×2 排列，避免 3 按钮挤一行出现「…」
        buttons: list[dict[str, Any]] = [
            upload_button,
            {"text": "提交登记", "style": 1, "key": "register_submit"},
            {"text": "取消", "style": 2, "key": "register_cancel"},
            {
                "text": "问题清单",
                "style": 4,
                "type": 1,
                "url": issue_list_url,
            },
        ]
    else:
        # 无第四按钮时：上传入口放正文区链接，底部仅保留 2 个宽按钮
        if upload_url:
            for item in horizontal:
                if item.get("keyname") == "图片":
                    item["value"] = (
                        f"已传{image_count}张·续传" if image_count else "点击上传图片"
                    )[:26]
                    item["type"] = 1
                    item["url"] = upload_url
                    break
        buttons = [
            {"text": "提交登记", "style": 1, "key": "register_submit"},
            {"text": "取消", "style": 2, "key": "register_cancel"},
        ]
        _append_issue_list_link(horizontal)

    button_selection = None
    if system_options:
        button_selection = build_button_selection(
            options=system_options,
            selected_id=selected_system_id,
        )

    return build_button_interaction_card(
        title="需求登记确认",
        desc="选择系统后提交登记"[:30],
        sub_title=f"需求内容：{preview}",
        task_id=task_id or new_task_id(),
        horizontal_items=horizontal,
        button_selection=button_selection,
        buttons=buttons,
        source_desc="需求登记",
    )


def build_register_success_card(
    *,
    task_id: str,
    demand_content: str,
    image_count: int = 0,
    system_name: str = "",
) -> dict[str, Any]:
    preview = demand_content[:80] + ("…" if len(demand_content) > 80 else "")
    horizontal: list[dict[str, Any]] = [
        {"keyname": "状态", "value": "已登记"},
        {"keyname": "字段", "value": "f9VtuW"},
    ]
    if system_name:
        horizontal.append({"keyname": "所属系统", "value": system_name[:26]})
    if image_count:
        horizontal.append({"keyname": "图片", "value": f"{image_count} 张"})
    _append_issue_list_link(horizontal)

    issue_list_url = get_settings().issue_list_url.strip()
    success_button: dict[str, Any] = {"text": "已完成", "style": 1, "key": "register_done"}
    if issue_list_url:
        success_button = {
            "text": "产品经理已开始跟进",
            "style": 4,
            "type": 1,
            "url": issue_list_url,
        }

    return build_button_interaction_card(
        title="登记成功",
        desc="已写入智能表格",
        sub_title=f"需求内容：{preview}",
        task_id=task_id,
        horizontal_items=horizontal,
        buttons=[success_button],
        source_desc="需求登记",
    )


def build_register_failed_card(*, task_id: str, error: str) -> dict[str, Any]:
    return build_button_interaction_card(
        title="登记失败",
        desc="写入智能表格时出错",
        sub_title=error[:112],
        task_id=task_id,
        horizontal_items=[
            {"keyname": "状态", "value": "失败"},
        ],
        buttons=[
            {"text": "请重试", "style": 2, "key": "register_retry_hint"},
        ],
        source_desc="需求登记",
    )


def build_register_cancelled_card(*, task_id: str) -> dict[str, Any]:
    return build_button_interaction_card(
        title="已取消登记",
        desc="未写入智能表格",
        task_id=task_id,
        horizontal_items=[
            {"keyname": "状态", "value": "已取消"},
        ],
        buttons=[
            {"text": "关闭", "style": 2, "key": "register_done"},
        ],
        source_desc="需求登记",
    )


def build_register_session_expired_card(*, task_id: str) -> dict[str, Any]:
    return build_button_interaction_card(
        title="登记已结束",
        desc="会话不存在或已提交",
        sub_title="如需再次登记，请重新发送「登记 需求内容」",
        task_id=task_id,
        horizontal_items=[
            {"keyname": "状态", "value": "已结束"},
        ],
        buttons=[
            {"text": "知道了", "style": 4, "key": "register_done"},
        ],
        source_desc="需求登记",
    )


def build_launch_test_reminder_card(
    *,
    demand_content: str,
    system_name: str = "",
    feedback_url: str = "",
) -> dict[str, Any]:
    preview = demand_content[:80] + ("…" if len(demand_content) > 80 else "")
    horizontal: list[dict[str, Any]] = [
        {"keyname": "状态", "value": "已上线"},
        {"keyname": "提醒", "value": "请尽快测试"},
    ]
    if system_name:
        horizontal.insert(1, {"keyname": "所属系统", "value": system_name[:26]})
    _append_issue_list_link(horizontal)

    issue_list_url = get_settings().issue_list_url.strip()
    buttons: list[dict[str, Any]] = []
    if feedback_url:
        buttons.append(
            {
                "text": "去评价",
                "style": 1,
                "type": 1,
                "url": feedback_url,
            }
        )
    else:
        buttons.append({"text": "知道了", "style": 4, "key": "launch_test_ack"})
    if issue_list_url:
        buttons.insert(
            0,
            {
                "text": "打开问题清单",
                "style": 1,
                "type": 1,
                "url": issue_list_url,
            },
        )

    return build_button_interaction_card(
        title="需求已上线，请测试",
        desc="产品经理已标记上线",
        sub_title=f"需求内容：{preview or '（无）'}",
        task_id=new_task_id(),
        horizontal_items=horizontal,
        buttons=buttons,
        source_desc="上线测试提醒",
    )


def _append_issue_list_link(horizontal: list[dict[str, Any]]) -> None:
    issue_list_url = get_settings().issue_list_url.strip()
    if issue_list_url:
        horizontal.append(
            {
                "keyname": "问题清单",
                "value": "打开问题清单"[:26],
                "type": 1,
                "url": issue_list_url,
            }
        )
