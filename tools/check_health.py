# -*- coding: utf-8 -*-
"""
check_health.py - 校验 /api/health 的响应体

核心断言: 响应里只允许出现"有没有", 绝不允许出现密钥或洛谷凭据本身。
这条规则写进 CI, 比写在文档里管用得多 —— 文档没人跑, 断言每次都跑。

注意: 读取时用 utf-8-sig 兜底, 因为 Windows 上 PowerShell 的 Set-Content -Encoding UTF8 会写 BOM,
而 CI 里 curl 下载的文件不该有 BOM —— 但本地测试会用 PowerShell 生成, 所以两种都要能读。

用法:
    python tools/check_health.py /tmp/health.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 响应体里绝对不许出现的字段名与片段
FORBIDDEN_FIELDS = ("api_key", "apikey", "secret", "token", "cookie", "password")
FORBIDDEN_SNIPPETS = ("LUOGU_CLIENT_ID", "LUOGU_UID", "__client_id", "_uid", "x-api-key")


def read_text(path: Path) -> str:
    """读文件并去掉可能的 UTF-8 BOM。"""
    return path.read_text(encoding="utf-8-sig")


def check(payload_text: str) -> list[str]:
    """返回问题清单; 空列表表示通过。"""
    problems: list[str] = []
    try:
        data = json.loads(payload_text)
    except ValueError as exc:
        return ["health 响应不是合法 JSON: " + str(exc)]
    if not isinstance(data, dict):
        return ["health 响应不是 JSON 对象"]
    if data.get("ok") is not True:
        problems.append("ok 字段不为 True: " + repr(data.get("ok")))

    # 顶层字段白名单: 多了就是泄漏
    allowed = {"ok", "model", "base_host", "has_key", "punch_ready", "version"}
    for key in data:
        if key not in allowed:
            problems.append("health 响应出现未预期字段: " + str(key))

    # 嵌套检查: 任何层级都不许出现敏感字段名
    def walk(node, path):
        if isinstance(node, dict):
            for key, value in node.items():
                low = str(key).lower()
                if low in FORBIDDEN_FIELDS:
                    problems.append("响应体里出现敏感字段: " + path + "." + str(key))
                walk(value, path + "." + str(key))
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, path + "[" + str(index) + "]")

    walk(data, "$")

    blob = json.dumps(data, ensure_ascii=False)
    for snippet in FORBIDDEN_SNIPPETS:
        if snippet in blob:
            problems.append("响应体里出现敏感片段: " + snippet)

    return problems


def main(argv=None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if not args:
        print("用法: python tools/check_health.py <health.json>", file=sys.stderr)
        return 2
    path = Path(args[0])
    if not path.is_file():
        print("找不到文件: " + str(path), file=sys.stderr)
        return 2
    problems = check(read_text(path))
    if problems:
        print("[FAIL] health 响应校验未通过:", file=sys.stderr)
        for item in problems:
            print("  - " + item, file=sys.stderr)
        return 1
    print("health 响应校验通过: 字段白名单内, 且不含任何密钥或凭据")
    return 0


if __name__ == "__main__":
    sys.exit(main())
