# coding: utf-8
"""运行配置，优先从环境变量读取。"""

import os
from pathlib import Path

from dotenv import load_dotenv

# config.py 在 wsdw_multi_workflow/api/，示例根目录是 learn_note/example。
_EXAMPLE_ROOT = Path(__file__).resolve().parents[2]
_LOCAL_ROOT = Path(__file__).resolve().parents[1]
# 已导出的环境变量优先；其次本示例 .env；最后根目录共用 .env。
load_dotenv(_LOCAL_ROOT / ".env")
load_dotenv(_EXAMPLE_ROOT / ".env")


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


# LLM 配置（请通过环境变量覆盖，勿提交真实密钥）
API_BASE = _env("WSDW_API_BASE", "https://api.deepseek.com")
API_KEY = _env("WSDW_API_KEY", "API_KEY")
MODEL_NAME = _env("WSDW_MODEL_NAME", "MODEL_NAME")
MODEL_PROVIDER = _env("WSDW_MODEL_PROVIDER", "OpenAI")
MODEL_ID = _env("WSDW_MODEL_ID", "MODEL_ID")

# 运行时开关
os.environ.setdefault("LLM_SSL_VERIFY", "false")
os.environ.setdefault("IS_SENSITIVE", "false")
