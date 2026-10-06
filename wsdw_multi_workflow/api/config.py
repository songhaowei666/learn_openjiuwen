# coding: utf-8
"""运行配置，优先从环境变量读取。"""

import os


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
