# coding: utf-8
"""CLI 入口：python -m backend.main [all|path|auth|token|static]

不接真实组织网关与真实模型，用本地假网关跑三课。
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from .lessons import (
    lesson_auth,
    lesson_path,
    lesson_token,
    lesson_wrong_static_token,
    run_all,
)


async def _async_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="openJiuwen 组织 LLM 网关接入学习 demo（假网关，无真实模型）",
    )
    parser.add_argument(
        "lesson",
        nargs="?",
        default="all",
        choices=["all", "path", "auth", "token", "static"],
        help="要运行的课程，默认 all",
    )
    args = parser.parse_args(argv)

    if args.lesson == "all":
        await run_all()
    elif args.lesson == "path":
        await lesson_path()
    elif args.lesson == "auth":
        await lesson_auth()
    elif args.lesson == "token":
        await lesson_token()
    elif args.lesson == "static":
        await lesson_wrong_static_token()
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_async_main()))


if __name__ == "__main__":
    main()
