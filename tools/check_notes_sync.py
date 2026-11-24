#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_notes_sync.py - 校验 notes/ 与 DOCX 原稿是否同步。

做法: 把 docs/draft/ 里的 DOCX 重新转一遍, 再与仓库里的 notes/ 逐字节比对。
只要有一处不一致 (哪怕只是少一个换行、一个空格), 就以退出码 1 结束。

为什么需要它: 笔记 Markdown 是从 DOCX 转出来的。一旦有人只改了 DOCX 或者只改了
Markdown, 两边就开始漂 —— 而 Markdown 不会报错, 漂了从肉眼看不出来, GitHub 上照常渲染。
所以把比对写成每次 CI 都跑的断言。

用法:
    python tools/check_notes_sync.py             # 校验仓库里的 notes/
    python tools/check_notes_sync.py --selftest  # 自检: 造差异, 断言比对器能抓到
"""

from __future__ import annotations

import filecmp
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List

REPO = Path(__file__).resolve().parent.parent
NOTES = REPO / "notes"
DOCX_DIR = REPO / "docs" / "draft"
CONVERTER = REPO / "tools" / "docx_to_md.py"


def compare_dirs(generated: Path, committed: Path) -> List[str]:
    """比对两个目录里的 Markdown 与图片, 返回问题清单。"""
    problems: List[str] = []

    gen_md = {p.name for p in generated.glob("*.md")}
    com_md = {p.name for p in committed.glob("*.md")}
    for name in sorted(gen_md - com_md):
        problems.append("仓库里少了转换结果中的文件: " + name)
    for name in sorted(com_md - gen_md):
        problems.append("仓库里多了转换结果里没有的文件: " + name)
    for name in sorted(gen_md & com_md):
        if not filecmp.cmp(generated / name, committed / name, shallow=False):
            problems.append("内容与转换结果不一致: " + name)

    gen_img = generated / "images"
    com_img = committed / "images"
    if gen_img.is_dir():
        gen_png = {p.name for p in gen_img.glob("*.png")}
        com_png = {p.name for p in com_img.glob("*.png")} if com_img.is_dir() else set()
        for name in sorted(gen_png - com_png):
            problems.append("仓库里少了图片: images/" + name)
        for name in sorted(com_png - gen_png):
            problems.append("仓库里多了图片: images/" + name)
        for name in sorted(gen_png & com_png):
            if not filecmp.cmp(gen_img / name, com_img / name, shallow=False):
                problems.append("图片与转换结果不一致: images/" + name)

    return problems


def run_conversion(docx: Path, out_dir: Path) -> int:
    cmd = [
        sys.executable, str(CONVERTER),
        "--input", str(docx),
        "--out-dir", str(out_dir),
        "--split",
        "--no-copy-docx",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    for line in (proc.stdout or "").splitlines():
        if "缺失" in line or "封面标题" in line:
            print("  " + line.strip())
    return proc.returncode


def selftest() -> int:
    cases = 0
    failed = 0

    def build(tmp: Path, *, mutate: str = "") -> Path:
        a = tmp / "gen"
        b = tmp / "com"
        (a / "images").mkdir(parents=True, exist_ok=True)
        (b / "images").mkdir(parents=True, exist_ok=True)
        (a / "01.md").write_text("正文\n", encoding="utf-8")
        (b / "01.md").write_text("正文\n", encoding="utf-8")
        (a / "images" / "pic1.png").write_bytes(b"PNG1")
        (b / "images" / "pic1.png").write_bytes(b"PNG1")
        if mutate == "text":
            (b / "01.md").write_text("正文改了\n", encoding="utf-8")
        elif mutate == "missing":
            (b / "01.md").unlink()
        elif mutate == "extra":
            (b / "02.md").write_text("多出来的\n", encoding="utf-8")
        elif mutate == "image":
            (b / "images" / "pic1.png").write_bytes(b"PNG2")
        return tmp

    def expect(label: str, problems: List[str], should_fail: bool) -> None:
        nonlocal cases, failed
        cases += 1
        ok = (len(problems) > 0) if should_fail else (len(problems) == 0)
        if not ok:
            failed += 1
            print("  [FAIL] %s -> %s" % (label, problems or "本该有问题却没抓到"))

    tmp = Path(tempfile.mkdtemp(prefix="notes-sync-selftest-"))
    try:
        d = build(tmp / "good")
        expect("完全一致要放行", compare_dirs(d / "gen", d / "com"), False)

        for mutate, label in [("text", "正文不一致"), ("missing", "少了文件"),
                              ("extra", "多了文件"), ("image", "图片不一致")]:
            d = build(tmp / mutate, mutate=mutate)
            expect(label + "要抓到", compare_dirs(d / "gen", d / "com"), True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("自检结果: %d passed / %d failed" % (cases - failed, failed))
    return 0 if failed == 0 else 1


def main(argv=None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if args and args[0] == "--selftest":
        return selftest()

    docx_files = sorted(DOCX_DIR.glob("*.docx"))
    if not docx_files:
        print("[FAIL] docs/draft/ 下没有 DOCX 原稿", file=sys.stderr)
        return 1

    tmp = Path(tempfile.mkdtemp(prefix="notes-sync-"))
    try:
        out_dir = tmp / "generated"
        rc = run_conversion(docx_files[0], out_dir)
        if rc != 0:
            print("[FAIL] 转换器返回码非 0: %d" % rc, file=sys.stderr)
            return 1
        problems = compare_dirs(out_dir, NOTES)
        gen_count = len(list(out_dir.glob("*.md")))
        print("转换结果: %d 篇 Markdown, 与仓库 notes/ 比对中" % gen_count)
        if problems:
            print("[FAIL] notes/ 与 DOCX 原稿不同步:", file=sys.stderr)
            for item in problems:
                print("  - " + item, file=sys.stderr)
            return 1
        print("[OK] notes/ 与 DOCX 原稿逐字节一致, 重新转换不会产生任何差异")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
