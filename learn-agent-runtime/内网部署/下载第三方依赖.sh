#!/usr/bin/env bash
# 从 foundation、management、service、server 的 pyproject.toml 收集第三方依赖并下载 wheel。
# 不下载这四个本仓库源码包，内网直接使用仓库源码：
#   openjiuwen-runtime-foundation
#   openjiuwen-runtime-management
#   openjiuwen-runtime-service
#   agent-runtime-server
#
# 默认按内网 Linux x86_64、Python 3.11 下载。目标机器不是这个平台时，先改下面两个变量。
# 可用值见：uv pip compile --help 中的 --python-platform。

set -euo pipefail

PYTHON_VERSION="${PYTHON_VERSION:-3.11}"
PYTHON_PLATFORM="${PYTHON_PLATFORM:-x86_64-manylinux2014}"
INDEX_URL="${INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
TRUSTED_HOST="${TRUSTED_HOST:-pypi.tuna.tsinghua.edu.cn}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -L)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "${SCRIPT_DIR}/../.." && pwd -L)}"
OUT_DIR="${SCRIPT_DIR}/wheels"
REQ_IN="${SCRIPT_DIR}/requirements.in"
REQ_TXT="${SCRIPT_DIR}/requirements.txt"

for pkg in foundation management service server; do
    if [[ ! -f "${PROJECT_ROOT}/${pkg}/pyproject.toml" ]]; then
        echo "未找到 ${PROJECT_ROOT}/${pkg}/pyproject.toml" >&2
        echo "请在 agent-runtime 仓库里执行：bash learn-agent-runtime/内网部署/下载第三方依赖.sh" >&2
        exit 1
    fi
done

mkdir -p "${OUT_DIR}"

# 这四个包用源码，wheel 目录里不保留它们
rm -f \
    "${OUT_DIR}"/openjiuwen_runtime_foundation-*.whl \
    "${OUT_DIR}"/openjiuwen_runtime_management-*.whl \
    "${OUT_DIR}"/openjiuwen_runtime_service-*.whl \
    "${OUT_DIR}"/agent_runtime_server-*.whl

python3 - "${PROJECT_ROOT}" "${REQ_IN}" <<'PY'
import re
import sys
import tomllib
from pathlib import Path

project_root = Path(sys.argv[1])
req_in = Path(sys.argv[2])

exclude = {
    "openjiuwen-runtime-foundation",
    "openjiuwen-runtime-management",
    "openjiuwen-runtime-service",
    "agent-runtime-server",
}
packages = ("foundation", "management", "service", "server")


def dist_name(requirement: str) -> str:
    base = re.split(r"[<>=!~\[]", requirement.strip(), maxsplit=1)[0]
    return base.strip().lower().replace("_", "-")


lines = []
seen = set()
for package in packages:
    pyproject = project_root / package / "pyproject.toml"
    with pyproject.open("rb") as file:
        data = tomllib.load(file)
    for requirement in data["project"]["dependencies"]:
        requirement = requirement.strip()
        if dist_name(requirement) in exclude:
            continue
        if requirement in seen:
            continue
        seen.add(requirement)
        lines.append(requirement)

req_in.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"已写入直接依赖 {len(lines)} 条: {req_in}")
PY

echo "解析传递依赖，平台 ${PYTHON_PLATFORM}，Python ${PYTHON_VERSION}"
uv pip compile \
    "${REQ_IN}" \
    -o "${REQ_TXT}" \
    --python-version "${PYTHON_VERSION}" \
    --python-platform "${PYTHON_PLATFORM}" \
    --default-index "${INDEX_URL}" \
    --allow-insecure-host "${TRUSTED_HOST}" \
    --no-header \
    --no-annotate

case "${PYTHON_PLATFORM}" in
    x86_64-manylinux2014) PIP_PLATFORM="manylinux2014_x86_64" ;;
    aarch64-manylinux2014) PIP_PLATFORM="manylinux2014_aarch64" ;;
    aarch64-apple-darwin) PIP_PLATFORM="macosx_11_0_arm64" ;;
    x86_64-apple-darwin) PIP_PLATFORM="macosx_10_12_x86_64" ;;
    *)
        echo "不支持的 PYTHON_PLATFORM: ${PYTHON_PLATFORM}" >&2
        exit 1
        ;;
esac

PY_TAG="${PYTHON_VERSION//./}"

echo "下载 wheel 到 ${OUT_DIR}"
python3 -m pip download \
    -r "${REQ_TXT}" \
    -d "${OUT_DIR}" \
    --no-deps \
    -i "${INDEX_URL}" \
    --trusted-host "${TRUSTED_HOST}" \
    --python-version "${PY_TAG}" \
    --platform "${PIP_PLATFORM}" \
    --implementation cp \
    --abi "cp${PY_TAG}" \
    --only-binary=:all:

echo "完成。第三方 wheel 在 ${OUT_DIR}，清单在 ${REQ_TXT}"
