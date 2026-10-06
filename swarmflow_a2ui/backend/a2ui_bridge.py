# coding: utf-8
"""把 human 节点的 prompt 标记转成 A2UI v0.9 消息。

标记写在提示词首行：
[approval] 审批按钮
[choice:value=标签|value=标签] 单选
[text] 文本输入
"""

from __future__ import annotations

CATALOG_ID = "https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json"


def visible_prompt(prompt: str) -> str:
    """去掉首行交互标记，留下给用户看的说明。"""
    return _parse(prompt)[1]


def build_human_surface(surface_id: str, prompt: str, label: str) -> list[dict]:
    """生成 createSurface、updateComponents、updateDataModel。"""
    kind, text, options = _parse(prompt)
    if kind == "approval":
        components, data = _approval(text)
    elif kind == "choice":
        components, data = _choice(text, options)
    else:
        components, data = _text(text, label)
    return [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": surface_id, "catalogId": CATALOG_ID},
        },
        {
            "version": "v0.9",
            "updateComponents": {"surfaceId": surface_id, "components": components},
        },
        {
            "version": "v0.9",
            "updateDataModel": {"surfaceId": surface_id, "path": "/", "value": data},
        },
    ]


def delete_surface(surface_id: str) -> list[dict]:
    """human 节点结束后销毁对应 Surface。"""
    return [{"version": "v0.9", "deleteSurface": {"surfaceId": surface_id}}]


def _parse(prompt: str) -> tuple[str, str, list[tuple[str, str]]]:
    """解析首行标记，返回交互类型、正文和选项。"""
    header, _, rest = prompt.partition("\n")
    header = header.strip()
    body = rest.strip() or prompt.strip()
    if header == "[approval]":
        return "approval", body, []
    if header == "[text]":
        return "text", body, []
    if header.startswith("[choice:") and header.endswith("]"):
        options: list[tuple[str, str]] = []
        raw = header[len("[choice:"):-1]
        for part in raw.split("|"):
            if "=" not in part:
                continue
            value, option_label = part.split("=", 1)
            value = value.strip()
            option_label = option_label.strip()
            if value and option_label:
                options.append((value, option_label))
        if options:
            return "choice", body, options
    return "text", prompt.strip(), []


def _approval(text: str) -> tuple[list[dict], dict]:
    """通过 / 驳回，驳回理由可选。"""
    components = [
        {"id": "root", "component": "Column", "children": ["prompt", "reason", "actions"]},
        {"id": "prompt", "component": "Text", "text": {"path": "/prompt"}, "variant": "body"},
        {
            "id": "reason",
            "component": "TextField",
            "label": {"path": "/reasonLabel"},
            "value": {"path": "/reason"},
            "variant": "longText",
        },
        {"id": "actions", "component": "Row", "children": ["approve", "reject"]},
        {
            "id": "approve",
            "component": "Button",
            "child": "approve-label",
            "variant": "primary",
            "action": {"event": {"name": "approve", "context": {"reason": {"path": "/reason"}}}},
        },
        {"id": "approve-label", "component": "Text", "text": {"path": "/approveLabel"}},
        {
            "id": "reject",
            "component": "Button",
            "child": "reject-label",
            "variant": "default",
            "action": {"event": {"name": "reject", "context": {"reason": {"path": "/reason"}}}},
        },
        {"id": "reject-label", "component": "Text", "text": {"path": "/rejectLabel"}},
    ]
    data = {
        "prompt": text,
        "reasonLabel": "驳回理由（可选）",
        "reason": "",
        "approveLabel": "通过",
        "rejectLabel": "驳回",
    }
    return components, data


def _choice(text: str, options: list[tuple[str, str]]) -> tuple[list[dict], dict]:
    """单选后提交。ChoicePicker 的值是字符串数组。"""
    components = [
        {"id": "root", "component": "Column", "children": ["prompt", "picker", "submit"]},
        {"id": "prompt", "component": "Text", "text": {"path": "/prompt"}, "variant": "body"},
        {
            "id": "picker",
            "component": "ChoicePicker",
            "label": {"path": "/pickerLabel"},
            "variant": "mutuallyExclusive",
            "displayStyle": "checkbox",
            "options": [{"label": label, "value": value} for value, label in options],
            "value": {"path": "/style"},
        },
        {
            "id": "submit",
            "component": "Button",
            "child": "submit-label",
            "variant": "primary",
            "action": {"event": {"name": "submit", "context": {"style": {"path": "/style"}}}},
        },
        {"id": "submit-label", "component": "Text", "text": {"path": "/submitLabel"}},
    ]
    data = {
        "prompt": text,
        "pickerLabel": "报告风格",
        "style": [options[0][0]],
        "submitLabel": "确认",
    }
    return components, data


def _text(text: str, label: str) -> tuple[list[dict], dict]:
    """单行或长文本输入。"""
    components = [
        {"id": "root", "component": "Column", "children": ["prompt", "focus", "submit"]},
        {"id": "prompt", "component": "Text", "text": {"path": "/prompt"}, "variant": "body"},
        {
            "id": "focus",
            "component": "TextField",
            "label": {"path": "/focusLabel"},
            "value": {"path": "/focus"},
            "variant": "longText",
        },
        {
            "id": "submit",
            "component": "Button",
            "child": "submit-label",
            "variant": "primary",
            "action": {"event": {"name": "submit", "context": {"focus": {"path": "/focus"}}}},
        },
        {"id": "submit-label", "component": "Text", "text": {"path": "/submitLabel"}},
    ]
    data = {
        "prompt": text,
        "focusLabel": label or "补充内容",
        "focus": "",
        "submitLabel": "提交",
    }
    return components, data
