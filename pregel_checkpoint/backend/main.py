# -*- coding: UTF-8 -*-
"""CLI 入口：python -m backend.main [all|parallel|interrupt|reenter|idempotent]"""

from __future__ import annotations

import argparse
import asyncio
import sys

from .lessons import (
    lesson_interrupt,
    lesson_parallel,
    lesson_side_effect,
    run_all,
)
from .setup import CHECKPOINT_DB, ensure_checkpointer


async def _async_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="openJiuwen Pregel 与 Checkpointer 学习 demo（无模型）",
    )
    parser.add_argument(
        "lesson",
        nargs="?",
        default="all",
        choices=["all", "parallel", "interrupt", "reenter", "idempotent"],
        help="要运行的课程，默认 all",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="人机课用手输回复（默认自动回复）",
    )
    args = parser.parse_args(argv)

    await ensure_checkpointer()
    print(f"Checkpointer shelve: {CHECKPOINT_DB}")

    if args.lesson == "all":
        await run_all(interactive=args.interactive)
    elif args.lesson == "parallel":
        await lesson_parallel()
    elif args.lesson == "interrupt":
        await lesson_interrupt(interactive=args.interactive)
    elif args.lesson == "reenter":
        await lesson_side_effect(idempotent=False)
    elif args.lesson == "idempotent":
        await lesson_side_effect(idempotent=True)
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_async_main()))


if __name__ == "__main__":
    main()
