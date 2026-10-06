# coding: utf-8
"""CLI 入口：多工作流金融智能体交互。"""

from __future__ import annotations

import ast
import asyncio
import logging
import uuid
import warnings
from typing import Optional

warnings.filterwarnings("ignore")

from openjiuwen.core.common.logging import llm_logger, logger, prompt_logger
from openjiuwen.core.runner import Runner

from .agent_factory import create_financial_agent

llm_logger.set_level(logging.CRITICAL)
logger.set_level(logging.CRITICAL)
prompt_logger.set_level(logging.CRITICAL)


def extract_response(s: str) -> Optional[str]:
    """从字符串中提取 response 值。"""
    try:
        data = ast.literal_eval(s.strip())
        if isinstance(data, dict):
            return data.get("response")
    except (ValueError, SyntaxError):
        return s
    return s


async def main() -> None:
    """启动交互循环。"""
    financial_agent = create_financial_agent()

    print("\n========== wsdw_multi_workflow 金融智能体 ==========")
    print("命令说明:")
    print("  - 直接输入问题进行对话")
    print("  - 'quit' 或 'exit': 退出系统\n")

    conversation_id = str(uuid.uuid4())[:8]
    print(f"当前会话 ID: {conversation_id}")

    round_count = 0
    while True:
        try:
            print(f"\n{'=' * 30}第 {round_count + 1} 轮对话{'=' * 30}\n")
            user_input = input("\n请输入您的问题: ").strip()

            if user_input.lower() in ["quit", "exit", "退出"]:
                print("\n感谢使用，再见！")
                break

            if not user_input:
                print("输入不能为空，请重新输入")
                continue

            round_count += 1
            res = Runner.run_agent_streaming(
                financial_agent,
                inputs={
                    "query": user_input,
                    "conversation_id": conversation_id,
                },
            )

            print("助手回复: ", end="", flush=True)
            async for chunk in res:
                if hasattr(chunk, "payload") and chunk.payload:
                    if hasattr(chunk.payload, "data") and chunk.payload.data:
                        for data_frame in chunk.payload.data:
                            if hasattr(data_frame, "text"):
                                response = extract_response(data_frame.text)
                                print(response, end="", flush=True)
            print()

        except KeyboardInterrupt:
            print("\n\n检测到 Ctrl+C，正在退出...")
            break
        except Exception as e:
            logger.error(f"处理输入时发生错误: {e}")
            print(f"\n发生错误: {e}")
            print("请重新输入")


def run() -> None:
    """同步入口。"""
    asyncio.run(main())


if __name__ == "__main__":
    run()
