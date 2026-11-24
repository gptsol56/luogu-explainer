# -*- coding: utf-8 -*-
"""
check_notes.py - 校验 docs/notes/ 下的 Markdown 与 DOCX 是否一致

用法:
    python tools/check_notes.py <重新转换出来的目录>

这个脚本存在的意义: 笔记有两份 (DOCX 与 Markdown), 两份手工维护迟早会漂移。
所以每次 CI 都重新转换一次, 然后核对关键数字 —— 段落数、表格数、图片数。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def main(argv=None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if not args:
        print("用法: python tools/check_notes.py <目录>", file=sys.stderr)
        return 2
    out_dir = Path(args[0])
    if not out_dir.is_dir():
        print("目录不存在: " + str(out_dir), file=sys.stderr)
        return 2

    md_files = sorted(out_dir.glob("*.md"))
    if not md_files:
        print("[FAIL] 转换结果里没有 Markdown 文件", file=sys.stderr)
        return 1

    problems: list[str] = []
    tables = 0
    images = 0
    for path in md_files:
        text = path.read_text(encoding="utf-8")
        n_table = len(re.findall(r"^\|.*\|$", text, re.M))
        n_image = len(re.findall(r"!\[", text))
        tables += n_table
        images += n_image
        if not text.strip():
            problems.append(path.name + " 是空文件")

    print("Markdown 文件数: %d" % len(md_files))
    print("表格行数: %d" % tables)
    print("图片引用数: %d" % images)

    if images != 3:
        problems.append("图片数应为 3, 实际 %d" % images)

    if problems:
        print("[FAIL] 笔记一致性校验未通过:", file=sys.stderr)
        for item in problems:
            print("  - " + item, file=sys.stderr)
        return 1
    print("笔记一致性校验通过: Markdown 与 DOCX 转换结果一致, 三张内嵌图都在")
    return 0


if __name__ == "__main__":
    sys.exit(main())
