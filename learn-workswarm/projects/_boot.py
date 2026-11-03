"""练习环境引导。

使用仓库 ``.vscode/settings.json`` 里的解释器，例如：

  /Users/song/anaconda3/envs/deepstudy/bin/python learn-workswarm/projects/.../exercise.py

不要用 ``uv run`` / 不要新建仓库根 ``.venv`` 来跑这些练习。

说明：``jiuwenswarm-1/learn-workswarm`` 可能是指向其它目录的符号链接；
源码根以「含 designer_graph.py 的仓库」为准（通常从当前工作目录向上查找），
不要用本文件的 ``parents[N]`` 当源码根。
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

# 与 .vscode/settings.json 的 python.defaultInterpreterPath 对齐（仅作文档提示）
VSCODE_PYTHON = "/Users/song/anaconda3/envs/deepstudy/bin/python"

_SCHEMA_REL = Path("jiuwenswarm/common/schema/designer_graph.py")


def find_code_root() -> Path:
    """定位含真实 jiuwenswarm 源码的仓库根。"""
    env = (os.environ.get("JIUWENSWARM_CODE_ROOT") or "").strip()
    if env:
        root = Path(env).expanduser().resolve()
        if (root / _SCHEMA_REL).is_file():
            return root
        raise FileNotFoundError(
            f"JIUWENSWARM_CODE_ROOT={root} 下找不到 {_SCHEMA_REL}"
        )

    # 优先从「启动时的 cwd」向上找（文档要求在 jiuwenswarm-1 根目录执行）
    searched: list[Path] = []
    for start in (Path.cwd().resolve(), Path(__file__).resolve()):
        for candidate in (start, *start.parents):
            if candidate in searched:
                continue
            searched.append(candidate)
            if (candidate / _SCHEMA_REL).is_file():
                return candidate

    # 常见旁路：学习目录在 lean_openjiuwen，源码在同级 jiuwenswarm-1
    learn_anchor = Path(__file__).resolve().parents[2]  # .../learn-workswarm
    sibling = learn_anchor.parent / "jiuwenswarm-1"
    if (sibling / _SCHEMA_REL).is_file():
        return sibling.resolve()

    raise FileNotFoundError(
        "找不到 jiuwenswarm 源码根。请在 jiuwenswarm-1 仓库根目录执行，"
        "或设置环境变量 JIUWENSWARM_CODE_ROOT。"
    )


def ensure_repo_on_path() -> Path:
    root = find_code_root()
    root_s = str(root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    return root


def _load_module(module_name: str, file_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载模块: {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_designer_graph() -> ModuleType:
    """加载真实 designer_graph.py（绕过 schema 包 __init__，免 openjiuwen 依赖）。"""
    root = ensure_repo_on_path()
    labels_name = "jiuwenswarm.common.schema.designer_node_labels"
    graph_name = "jiuwenswarm.common.schema.designer_graph"
    if graph_name in sys.modules:
        return sys.modules[graph_name]

    schema_dir = root / "jiuwenswarm" / "common" / "schema"
    if labels_name not in sys.modules:
        _load_module(labels_name, schema_dir / "designer_node_labels.py")
    return _load_module(graph_name, schema_dir / "designer_graph.py")


REPO_ROOT = ensure_repo_on_path()
