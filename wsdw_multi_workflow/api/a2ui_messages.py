# coding: utf-8
"""把 Controller 输出编码为 A2UI v0.9 消息。"""

from __future__ import annotations

import ast
import uuid
from typing import Any, Optional

# 与 @a2ui/react basicCatalog.id 保持一致
BASIC_CATALOG_ID = "https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json"
A2UI_VERSION = "v0.9"


def extract_response(text: str) -> Optional[str]:
    """从字符串中提取 response 值。"""
    try:
        data = ast.literal_eval(text.strip())
        if isinstance(data, dict):
            response = data.get("response")
            if response is not None:
                return str(response)
            return str(data)
    except (ValueError, SyntaxError):
        return text
    return text


def _payload_kind(payload: Any) -> str:
    """读取 payload 事件类型名。"""
    event_type = getattr(payload, "type", None)
    name = getattr(event_type, "name", None)
    if name:
        return str(name).upper()
    return str(event_type or "").upper()


def _extract_chunk_text(chunk: Any) -> str:
    """从 Controller 输出块中取出可见文本。"""
    payload = getattr(chunk, "payload", None)
    if payload is None:
        return ""
    data = getattr(payload, "data", None)
    if not data:
        return ""
    parts: list[str] = []
    for data_frame in data:
        text = getattr(data_frame, "text", None)
        if text:
            extracted = extract_response(str(text))
            if extracted:
                parts.append(extracted)
    return "".join(parts).strip()


def _create_surface(surface_id: str) -> dict[str, Any]:
    return {
        "version": A2UI_VERSION,
        "createSurface": {
            "surfaceId": surface_id,
            "catalogId": BASIC_CATALOG_ID,
        },
    }


def _update_components(surface_id: str, components: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "version": A2UI_VERSION,
        "updateComponents": {
            "surfaceId": surface_id,
            "components": components,
        },
    }


def _update_data_model(surface_id: str, value: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": A2UI_VERSION,
        "updateDataModel": {
            "surfaceId": surface_id,
            "path": "/",
            "value": value,
        },
    }


def build_info_surface(surface_id: str, title: str, body: str) -> list[dict[str, Any]]:
    """构建普通回复卡片。"""
    return [
        _create_surface(surface_id),
        _update_components(
            surface_id,
            [
                {"id": "root", "component": "Card", "child": "content"},
                {
                    "id": "content",
                    "component": "Column",
                    "children": ["title", "body"],
                },
                {
                    "id": "title",
                    "component": "Text",
                    "text": {"path": "/title"},
                    "variant": "h3",
                },
                {
                    "id": "body",
                    "component": "Text",
                    "text": {"path": "/body"},
                    "variant": "body",
                },
            ],
        ),
        _update_data_model(surface_id, {"title": title, "body": body}),
    ]


def build_form_surface(surface_id: str, prompt: str) -> list[dict[str, Any]]:
    """构建工作流中断提问表单。"""
    return [
        _create_surface(surface_id),
        _update_components(
            surface_id,
            [
                {"id": "root", "component": "Card", "child": "content"},
                {
                    "id": "content",
                    "component": "Column",
                    "children": ["title", "prompt", "field", "submit"],
                },
                {
                    "id": "title",
                    "component": "Text",
                    "text": {"path": "/title"},
                    "variant": "h3",
                },
                {
                    "id": "prompt",
                    "component": "Text",
                    "text": {"path": "/prompt"},
                    "variant": "body",
                },
                {
                    "id": "field",
                    "component": "TextField",
                    "label": {"path": "/fieldLabel"},
                    "value": {"path": "/answer"},
                    "variant": "shortText",
                },
                {
                    "id": "submit",
                    "component": "Button",
                    "child": "submit-label",
                    "variant": "primary",
                    "action": {
                        "event": {
                            "name": "submit_answer",
                            "context": {"answer": {"path": "/answer"}},
                        }
                    },
                },
                {
                    "id": "submit-label",
                    "component": "Text",
                    "text": {"path": "/submitLabel"},
                },
            ],
        ),
        _update_data_model(
            surface_id,
            {
                "title": "需要补充信息",
                "prompt": prompt,
                "fieldLabel": "请输入",
                "answer": "",
                "submitLabel": "提交",
            },
        ),
    ]


def build_error_surface(surface_id: str, message: str) -> list[dict[str, Any]]:
    """构建错误卡片。"""
    return build_info_surface(surface_id, "办理失败", message)


def chunk_to_a2ui_messages(chunk: Any) -> list[dict[str, Any]]:
    """将单个 Controller 输出块转为 A2UI 消息列表。"""
    payload = getattr(chunk, "payload", None)
    if payload is None:
        return []

    kind = _payload_kind(payload)
    if kind in {"TASK_PROCESSING", "ALL_TASKS_PROCESSED"}:
        return []

    text = _extract_chunk_text(chunk)
    if not text:
        return []

    surface_id = f"turn-{uuid.uuid4().hex[:10]}"
    if kind == "TASK_INTERACTION":
        return build_form_surface(surface_id, text)
    if kind == "TASK_FAILED":
        return build_error_surface(surface_id, text)
    if kind == "TASK_COMPLETION":
        return build_info_surface(surface_id, "办理完成", text)
    return build_info_surface(surface_id, "助手回复", text)
