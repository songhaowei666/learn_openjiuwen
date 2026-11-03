#!/usr/bin/env python3
"""知识点 1.3：一项目一会话一画布

真实模块：gateway.common.work_mode
学习扩展：binding.validate_design_binding

用法：
  python learn-workswarm/projects/03-work-mode-binding/exercise.py
  python learn-workswarm/projects/03-work-mode-binding/exercise.py --cases
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _boot import REPO_ROOT  # noqa: E402

from gateway.common.work_mode import (  # noqa: E402
    DEFAULT_PROJECT_ID_CODE,
    DEFAULT_PROJECT_ID_WORK,
    DESIGN_WORK_MODE,
    EXECUTION_WORK_MODES,
    SUPPORTED_WORK_MODES,
    is_default_project_id,
    normalize_work_mode,
    resolve_default_project_id,
)

# 同目录学习模块
sys.path.insert(0, str(Path(__file__).resolve().parent))
from binding import uses_execution_profile, validate_design_binding  # noqa: E402

HERE = Path(__file__).resolve().parent


CASES = [
    {
        "name": "合法 design 绑定",
        "payload": {
            "work_mode": "design",
            "project_id": "proj_film_01",
            "session_id": "sess_abc",
            "graph_id": "graph_deadbeefcafebabe",
            "graph_project_id": "proj_film_01",
        },
        "expect_ok": True,
    },
    {
        "name": "误用 work 默认项目",
        "payload": {
            "work_mode": "design",
            "project_id": DEFAULT_PROJECT_ID_WORK,
            "session_id": "sess_abc",
            "graph_id": "graph_deadbeefcafebabe",
        },
        "expect_ok": False,
    },
    {
        "name": "误用 code 默认项目",
        "payload": {
            "work_mode": "design",
            "project_id": DEFAULT_PROJECT_ID_CODE,
            "session_id": "sess_abc",
            "graph_id": "graph_x",
        },
        "expect_ok": False,
    },
    {
        "name": "work_mode 不是 design",
        "payload": {
            "work_mode": "work",
            "project_id": "proj_film_01",
            "session_id": "sess_abc",
            "graph_id": "graph_x",
        },
        "expect_ok": False,
    },
    {
        "name": "graph 与 session 项目不一致",
        "payload": {
            "work_mode": "design",
            "project_id": "proj_a",
            "session_id": "sess_abc",
            "graph_id": "graph_x",
            "graph_project_id": "proj_b",
        },
        "expect_ok": False,
    },
]


def print_work_mode_facts() -> None:
    print("\n=== 真实 work_mode 事实 ===")
    print(f"  SUPPORTED_WORK_MODES  = {sorted(SUPPORTED_WORK_MODES)}")
    print(f"  EXECUTION_WORK_MODES  = {sorted(EXECUTION_WORK_MODES)}")
    print(f"  DESIGN_WORK_MODE      = {DESIGN_WORK_MODE!r}")
    print(f"  design 走执行 profile? {uses_execution_profile('design')}")
    print(f"  work 走执行 profile?   {uses_execution_profile('work')}")
    print(f"  resolve_default(work)  = {resolve_default_project_id('work')!r}")
    print(f"  resolve_default(code)  = {resolve_default_project_id('code')!r}")
    print(f"  is_default('default')  = {is_default_project_id('default')}")
    print(f"  is_default('proj_x')   = {is_default_project_id('proj_x')}")
    print(f"  源码: {REPO_ROOT / 'gateway/common/work_mode.py'}")


def run_cases() -> int:
    print("\n=== 绑定用例 ===")
    failed = 0
    for case in CASES:
        result = validate_design_binding(**case["payload"])
        ok = result.ok == case["expect_ok"]
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {case['name']}: ok={result.ok} reason={result.reason}")
        if not ok:
            failed += 1
    return 1 if failed else 0


def check_my_session() -> int:
    path = HERE / "my_session.json"
    print(f"\n=== 练习验收: {path.name} ===")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if "FIXME" in json.dumps(raw, ensure_ascii=False):
        print("  还有 FIXME，请改成合法 design 绑定")
        return 1
    result = validate_design_binding(
        work_mode=raw.get("work_mode"),
        project_id=raw.get("project_id"),
        session_id=raw.get("session_id"),
        graph_id=raw.get("graph_id"),
        graph_project_id=raw.get("graph_project_id"),
    )
    if not result.ok:
        print(f"  失败: {result.reason}")
        return 1
    mode = normalize_work_mode(raw.get("work_mode"))
    if uses_execution_profile(mode):
        print("  失败: design 不应走 execution profile")
        return 1
    print("  OK: 一项目一会话一画布绑定合法")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="学习项目 03：work_mode 绑定")
    parser.add_argument("--cases", action="store_true", help="跑内置正反用例")
    parser.add_argument("--check", action="store_true", help="验收 my_session.json")
    args = parser.parse_args()

    print_work_mode_facts()
    if args.check:
        return check_my_session()
    if args.cases:
        return run_cases()

    print("\n下一步：")
    print("  python learn-workswarm/projects/03-work-mode-binding/exercise.py --cases")
    print("  编辑 my_session.json 后：")
    print("  python learn-workswarm/projects/03-work-mode-binding/exercise.py --check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
