"""需求登记「所属系统」下拉选项解析。"""

from __future__ import annotations

from typing import Any

SYSTEM_QUESTION_KEY = "demand_system"


def parse_option_list(raw: str) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    for index, part in enumerate(raw.split(",")):
        text = part.strip()
        if text:
            options.append({"id": f"sys_{index}", "text": text})
    return options


def default_option(options: list[dict[str, str]]) -> tuple[str, str]:
    if not options:
        return "", ""
    first = options[0]
    return first["id"], first["text"]


def label_for_option_id(options: list[dict[str, str]], option_id: str) -> str:
    for item in options:
        if item["id"] == option_id:
            return item["text"]
    return ""


def build_button_selection(*, options: list[dict[str, str]], selected_id: str) -> dict[str, Any]:
    selected = selected_id or (options[0]["id"] if options else "")
    return {
        "question_key": SYSTEM_QUESTION_KEY,
        "title": "所属系统",
        "disable": False,
        "option_list": options,
        "selected_id": selected,
    }


def parse_system_selection(
    selected_items: list[dict[str, Any]] | dict[str, Any] | None,
    *,
    options: list[dict[str, str]],
) -> tuple[str, str] | None:
    if not selected_items or not options:
        return None

    items = selected_items if isinstance(selected_items, list) else [selected_items]
    for item in items:
        if item.get("question_key") != SYSTEM_QUESTION_KEY:
            continue
        option_ids = (item.get("option_ids") or {}).get("option_id") or []
        if not option_ids:
            continue
        option_id = str(option_ids[0])
        label = label_for_option_id(options, option_id)
        if label:
            return option_id, label
    return None
