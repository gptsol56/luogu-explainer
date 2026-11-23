# -*- coding: utf-8 -*-
"""
check_assets.py - 校验提示词模板与演示样例这两个静态资源

用法:
    python tools/check_assets.py <tpl.json> <sample.json>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def check_template(path: Path) -> list[str]:
    problems: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return ["提示词模板读取失败: " + str(exc)]
    if not isinstance(data, dict):
        return ["提示词模板不是 JSON 对象"]
    sections = data.get("required_sections")
    if not isinstance(sections, list) or len(sections) < 6:
        problems.append("required_sections 少于 6 个小节")
    template = str(data.get("user_prompt_template") or "")
    for marker in ("{{style}}", "{{sections}}", "{{problem}}"):
        if marker not in template:
            problems.append("模板缺少占位符 " + marker)
    styles = data.get("styles")
    if not isinstance(styles, list) or not styles:
        problems.append("styles 为空")
    return problems


def check_sample(path: Path) -> list[str]:
    problems: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return ["演示样例读取失败: " + str(exc)]
    if not isinstance(data, dict):
        return ["演示样例不是 JSON 对象"]
    markdown = str(data.get("markdown") or "")
    if len(markdown) < 200:
        problems.append("演示样例正文过短: " + str(len(markdown)) + " 字符")
    for name in ("题目在考什么", "思路推导", "关键代码", "复杂度", "常见坑", "自测题"):
        if name not in markdown:
            problems.append("演示样例缺少小节: " + name)
    meta = str(data.get("meta") or "")
    if "预先生成" not in str(data.get("title") or "") + meta and "预生成" not in meta:
        problems.append("演示样例没有标注是预生成的")
    return problems


def main(argv=None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if len(args) < 2:
        print("用法: python tools/check_assets.py <tpl.json> <sample.json>", file=sys.stderr)
        return 2
    problems: list[str] = []
    problems += check_template(Path(args[0]))
    problems += check_sample(Path(args[1]))
    if problems:
        print("[FAIL] 静态资源校验未通过:", file=sys.stderr)
        for item in problems:
            print("  - " + item, file=sys.stderr)
        return 1
    print("静态资源校验通过: 模板小节齐全, 演示样例含全部固定小节且已标注预生成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
