#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把学习笔记 DOCX 转成 Markdown（按章拆分 + 内嵌图片提取 + 零丢失自检）。

默认输出**纯正文**: 不写 YAML frontmatter, 不写「本文件来自 DOCX…」说明行 ——
仓库里只留章节本身。需要元信息时加 --with-frontmatter。

用法::

    python tools/docx_to_md.py --input <docx> --out-dir <dir> --split

判定规则（来自对该 DOCX 的实测：所有段落 style 名都是 Normal，层级不靠样式名，
而是靠 run 的直接格式）：

* 21pt + 粗体 + 色 2F5D50                -> 文档主标题（H1）
* 16pt + 粗体 + 色 2F5D50                -> 章（H2）
* 13pt + 粗体 + 色 3E7A68                -> 节（H3）
* 11.5pt / 10.5pt + 粗体 + 色 3E7A68    -> 小节（H4）
* Consolas 字体                          -> 代码行（连续多行合并成一个围栏代码块）
* Calibri 10.0pt + 色 55655F + 左缩进 198 twips -> 引用块
* Calibri 10.5pt + 色 1A1A1A             -> 普通正文
* 表格                                   -> GitHub Markdown 表格（首行为表头，单元格内换行用 <br>）
* 空段落跳过；内嵌图片抽成 images/picN.png 并在正文原位引用

只依赖 python-docx + 标准库，不做 pip install，不修改 DOCX 本体。
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph
from docx.text.run import Run

# ---------------------------------------------------------------- 常量

A_BLIP = "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
R_EMBED = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"

COLOR_TITLE = "2F5D50"
COLOR_SECTION = "3E7A68"
COLOR_QUOTE = "55655F"
COLOR_BODY = "1A1A1A"
CODE_FONT = "consolas"
QUOTE_INDENT_TWIPS = 198

FENCE = chr(96) * 3

DEFAULT_CHAPTER_FILES = {
    1: "01-Git-学习记录.md",
    2: "02-AI-Agent-学习记录.md",
    3: "03-提交日记-洛谷打卡助手.md",
    4: "04-把仓库做成一个完整的整体.md",
    5: "05-拆仓库-公开的站点与私有的笔记.md",
}
# 这里原本还有两张表: DEFAULT_CHAPTER_META（每章的标题与标签）和 DEFAULT_SUMMARY
# （我替「学习总结」写的那段总体总结），以及 SUMMARY_FILE / SUMMARY_META。
# 现在一并删掉, 原因很直接: 仓库只留笔记本身, 不留我生成的文字。
# 标题与标签是给索引用的元信息 —— 默认连 frontmatter 都不输出, 它更该走;
# 总体总结是我写的, 不是学习记录里的话, 更不该进仓库。


# ---------------------------------------------------------------- 数据结构


@dataclass
class Block:
    """一个转换单元：标题 / 正文 / 引用 / 代码 / 表格 / 图片。"""

    kind: str
    text: str = ""
    rows: List[List[str]] = field(default_factory=list)
    images: List[str] = field(default_factory=list)


# ---------------------------------------------------------------- 取值工具


def _run_props(run: Run) -> Tuple[Optional[str], Optional[float], bool, Optional[str]]:
    name = run.font.name
    size = run.font.size.pt if run.font.size is not None else None
    bold = bool(run.bold)
    color: Optional[str] = None
    try:
        if run.font.color is not None and run.font.color.type is not None:
            color = str(run.font.color.rgb)
    except (AttributeError, ValueError):
        color = None
    return name, size, bold, color


def dominant_props(par: Paragraph) -> Tuple[Optional[str], Optional[float], bool, Optional[str]]:
    """取文字最多的那个 run 的格式特征作为整段的判定依据。"""
    best = None
    best_len = -1
    for run in par.runs:
        length = len(run.text.strip())
        if length > best_len:
            best_len = length
            best = run
    if best is None:
        return None, None, False, None
    return _run_props(best)


def _near(size: Optional[float], target: float) -> bool:
    return size is not None and abs(size - target) < 0.01


def classify(par: Paragraph) -> str:
    name, size, bold, color = dominant_props(par)
    low = (name or "").lower()
    if CODE_FONT in low:
        return "code"
    if bold and color == COLOR_TITLE and _near(size, 21):
        return "h1"
    if bold and color == COLOR_TITLE and _near(size, 16):
        return "h2"
    if bold and color == COLOR_SECTION and _near(size, 13):
        return "h3"
    if bold and color == COLOR_SECTION and (_near(size, 11.5) or _near(size, 10.5)):
        return "h4"
    indent = par.paragraph_format.left_indent
    twips = indent.twips if indent is not None else None
    if (
        "calibri" in low
        and _near(size, 10.0)
        and color == COLOR_QUOTE
        and twips == QUOTE_INDENT_TWIPS
    ):
        return "quote"
    return "body"


def paragraph_segments(par: Paragraph) -> List[Tuple[str, str]]:
    """按文档顺序返回段落的 ('text'|'image', 值) 片段。"""
    segs: List[Tuple[str, str]] = []
    for child in par._p:
        if child.tag != qn("w:r"):
            continue
        run = Run(child, par)
        for blip in child.findall(".//" + A_BLIP):
            rid = blip.get(R_EMBED)
            if rid:
                segs.append(("image", rid))
        if run.text:
            segs.append(("text", run.text))
    return segs


# ---------------------------------------------------------------- 读取正文


def read_table_rows(tbl_el, doc) -> List[List[str]]:
    rows: List[List[str]] = []
    for tr in tbl_el.tr_lst:
        cells: List[str] = []
        for tc in tr.tc_lst:
            cell = _Cell(tc, doc)
            cells.append(cell.text)
        rows.append(cells)
    return rows


def build_blocks(doc, images_dir: str) -> Tuple[List[Block], Dict[str, str], int]:
    """遍历 body，产出块序列；同时给每张内嵌图片编号并抽出二进制。"""
    blocks: List[Block] = []
    rid_to_name: Dict[str, str] = {}
    saved = 0

    for el in doc.element.body:
        if el.tag == qn("w:p"):
            par = Paragraph(el, doc)
            segs = paragraph_segments(par)
            text = "".join(v for k, v in segs if k == "text")
            rids = [v for k, v in segs if k == "image"]
            if not text.strip() and not rids:
                continue  # 空段落跳过
            kind = classify(par)
            if kind == "code":
                blocks.append(Block("code", text=text, images=list(rids)))
            else:
                if text.strip():
                    blocks.append(Block(kind, text=text))
                for rid in rids:
                    blocks.append(Block("image", text=rid))
        elif el.tag == qn("w:tbl"):
            rows = read_table_rows(el, doc)
            if rows:
                blocks.append(Block("table", rows=rows))

    # 图片按文档顺序编号并落盘
    for block in blocks:
        if block.kind == "image":
            rid = block.text
            if rid in rid_to_name:
                block.text = rid_to_name[rid]
                continue
            part = doc.part.related_parts[rid]
            ext = ".png" if "png" in (part.content_type or "") else ".jpg"
            name = "pic%d%s" % (saved + 1, ext)
            rid_to_name[rid] = name
            block.text = name
            saved += 1
            (Path(images_dir) / name).write_bytes(part.blob)
        elif block.kind == "code":
            for i, rid in enumerate(block.images):
                if rid in rid_to_name:
                    block.images[i] = rid_to_name[rid]
                    continue
                part = doc.part.related_parts[rid]
                ext = ".png" if "png" in (part.content_type or "") else ".jpg"
                name = "pic%d%s" % (saved + 1, ext)
                rid_to_name[rid] = name
                block.images[i] = name
                saved += 1
                (Path(images_dir) / name).write_bytes(part.blob)

    return blocks, rid_to_name, saved


# ---------------------------------------------------------------- 渲染


def render_table(rows: List[List[str]]) -> List[str]:
    ncols = max(len(r) for r in rows)

    def fmt(cells: Sequence[str]) -> str:
        cells = list(cells) + [""] * (ncols - len(cells))
        cells = [
            c.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>").replace("|", "\\|")
            for c in cells[:ncols]
        ]
        return "| " + " | ".join(cells) + " |"

    out = [fmt(rows[0]), "|" + "|".join([" --- "] * ncols) + "|"]
    for row in rows[1:]:
        out.append(fmt(row))
    return out


def render(blocks: Sequence[Block], level_shift: int = 0, image_prefix: str = "images/") -> List[str]:
    """把块序列渲染成 Markdown 行；level_shift=1 表示标题层级整体上提一级。"""
    lines: List[str] = []
    i = 0
    n = len(blocks)
    while i < n:
        block = blocks[i]
        kind = block.kind
        if kind in ("h1", "h2", "h3", "h4"):
            level = max(1, int(kind[1]) - level_shift)
            lines.append("%s %s" % ("#" * level, block.text.strip()))
            lines.append("")
        elif kind == "body":
            lines.append(block.text.rstrip())
            lines.append("")
        elif kind == "quote":
            quoted = ["> " + ln if ln.strip() else ">" for ln in block.text.split("\n")]
            lines.extend(quoted)
            lines.append("")
        elif kind == "image":
            lines.append("![](%s%s)" % (image_prefix, block.text))
            lines.append("")
        elif kind == "code":
            code_lines: List[str] = []
            images: List[str] = []
            j = i
            while j < n and blocks[j].kind == "code":
                code_lines.extend(blocks[j].text.split("\n"))
                images.extend(blocks[j].images)
                j += 1
            fence = FENCE
            while any(ln.strip().startswith(fence) for ln in code_lines):
                fence += chr(96)
            lines.append(fence)
            lines.extend(code_lines)
            lines.append(fence)
            lines.append("")
            for name in images:
                lines.append("![](%s%s)" % (image_prefix, name))
                lines.append("")
            i = j - 1
        elif kind == "table":
            lines.extend(render_table(block.rows))
            lines.append("")
        i += 1
    return lines


# ---------------------------------------------------------------- 拆分


def split_chapters(blocks: Sequence[Block]) -> Tuple[Optional[Block], List[Tuple[str, List[Block]]]]:
    title_block: Optional[Block] = None
    chapters: List[Tuple[str, List[Block]]] = []
    cur_title = ""
    cur: List[Block] = []
    for block in blocks:
        if block.kind == "h1" and title_block is None:
            title_block = block
            continue
        if block.kind == "h2":
            if cur:
                chapters.append((cur_title, cur))
            cur_title = block.text.strip()
            cur = [block]
            continue
        cur.append(block)
    if cur:
        chapters.append((cur_title, cur))
    return title_block, chapters


# ---------------------------------------------------------------- 零丢失自检

_MD_PREFIX = re.compile(r"^\s*(?:#{1,6}\s+|>\s?|[-*]\s+|\|)")
_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    """去掉行首 markdown 标记并把空白折叠成单空格，用于指纹比对。"""
    kept = []
    for line in text.split("\n"):
        kept.append(_MD_PREFIX.sub("", line, count=1))
    return _WS.sub(" ", " ".join(kept)).strip()


def fingerprint(text: str, size: int = 20) -> str:
    return normalize(text)[:size]


# ---------------------------------------------------------------- 输出


def yaml_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def front_matter(meta: Dict[str, object], source: str, chapter: str, date: str) -> List[str]:
    tags = meta.get("tags") or []
    tag_text = "[" + ", ".join(yaml_quote(str(t)) for t in tags) + "]"
    return [
        "---",
        "title: %s" % yaml_quote(str(meta.get("title", ""))),
        "date: %s" % yaml_quote(date),
        "tags: %s" % tag_text,
        "source: %s" % yaml_quote(source),
        "chapter: %s" % yaml_quote(chapter),
        "---",
        "",
    ]


def write_text(path: Path, lines: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines).rstrip("\n") + "\n")


def sanitize_filename(title: str) -> str:
    name = re.sub(r"[\\/:*?\"<>|\r\n]+", "", title).strip()
    name = re.sub(r"^[一二三四五六七八九十]+、\s*", "", name)
    return name or "chapter"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- 主流程


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="把学习笔记 DOCX 转成 Markdown")
    parser.add_argument("--input", required=True, help="源 .docx 路径")
    parser.add_argument("--out-dir", required=True, help="输出目录")
    parser.add_argument("--split", action="store_true", help="按章拆分成多个文件")
    parser.add_argument("--images-subdir", default="images", help="图片子目录名（相对 out-dir）")
    parser.add_argument("--copy-docx", dest="copy_docx", action="store_true", default=True,
                        help="把源 DOCX 原样复制一份到输出目录（默认开）")
    parser.add_argument("--no-copy-docx", dest="copy_docx", action="store_false",
                        help="不复制源 DOCX")
    parser.add_argument("--copy-name", default="淳阳项目组学习笔记_第一阶段.docx",
                        help="复制后的文件名")
    parser.add_argument("--with-frontmatter", dest="with_frontmatter", action="store_true",
                        help="额外输出 YAML frontmatter 与来源说明行（默认不输出, 只留纯正文）")
    parser.add_argument("--date", default=None, help="front matter 日期（默认今天, 仅 --with-frontmatter 有效）")
    args = parser.parse_args(list(argv) if argv is not None else None)

    src = Path(args.input)
    out_dir = Path(args.out_dir)
    if not src.is_file():
        print("[错误] 输入文件不存在：%s" % src, file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)
    images_dir = out_dir / args.images_subdir
    images_dir.mkdir(parents=True, exist_ok=True)

    doc = Document(str(src))
    all_paras = doc.paragraphs
    blocks, rid_to_name, image_count = build_blocks(doc, str(images_dir))

    date = args.date or datetime.date.today().isoformat()
    source_name = src.name
    title_block, chapters = split_chapters(blocks)

    outputs: List[Tuple[str, List[str]]] = []
    total_lines = 0
    table_count = 0
    table_rows = 0

    if args.split:
        for idx, (chapter_title, chapter_blocks) in enumerate(chapters, start=1):
            filename = DEFAULT_CHAPTER_FILES.get(idx) or (
                "%02d-%s.md" % (idx, sanitize_filename(chapter_title))
            )
            body = render(chapter_blocks, level_shift=1, image_prefix=args.images_subdir + "/")
            lines = []
            if args.with_frontmatter:
                meta = {"title": chapter_title, "tags": ["学习笔记"]}
                lines.extend(front_matter(meta, source_name, chapter_title, date))
                lines.append("> 本文件来自 DOCX《%s》的「%s」一章。" % (source_name, chapter_title))
                lines.append("")
            lines.extend(body)
            outputs.append((filename, lines))
    else:
        body = render(blocks, level_shift=0, image_prefix=args.images_subdir + "/")
        lines = []
        if args.with_frontmatter:
            meta = {"title": title_block.text.strip() if title_block else source_name, "tags": ["学习笔记"]}
            lines.extend(front_matter(meta, source_name, "全文", date))
            lines.append("> 本文件来自 DOCX《%s》的完整内容。" % source_name)
            lines.append("")
        lines.extend(body)
        outputs.append(("notes.md", lines))

    # 原来这里还会生成一个「学习总结」文件（主标题 + 第三章 3.5 + 总体总结）。
    # 现在不生成了: 3.5 我的想法本来就在第三章正文里, 总体总结是我替用户写的总结,
    # 属于「我生成的文字」, 与「仓库只留笔记本身」冲突。留一句说明, 比留一段凑数的总结好。

    written: List[Path] = []
    for filename, lines in outputs:
        path = out_dir / filename
        write_text(path, lines)
        written.append(path)
        total_lines += len(lines)
        table_count += sum(1 for ln in lines if ln.startswith("| "))
        table_rows += 0

    # 复制源 DOCX（二进制不变）
    copy_note = ""
    if args.copy_docx:
        dst = out_dir / args.copy_name
        shutil.copyfile(src, dst)
        same = sha256(src) == sha256(dst)
        copy_note = "复制 DOCX：%s（sha256 与源一致：%s）" % (dst.name, "是" if same else "否")

    # ---------------------------------------------------------- 零丢失核对
    out_text = "\n".join("\n".join(lines) for _, lines in outputs)
    norm_out = normalize(out_text)
    # 封面标题（DOCX 的 h1 主标题）有意不进章节正文: 它在 README 与 DOCX 封面里,
    # 而这一版转换器不再生成「学习总结」文件, 标题就没地方跟着走了。
    # 这里显式排除并单独报出来, 不藏起来 —— 零丢失核对如果偷偷少算一段, 那就不叫核对。
    title_text = title_block.text.strip() if title_block is not None else ""
    fingerprints: List[str] = []
    skipped_title = 0
    for par in all_paras:
        text = par.text.strip()
        if not text:
            continue
        if title_text and text == title_text:
            skipped_title += 1
            continue
        fingerprints.append(fingerprint(text))
    covered = 0
    missing: List[str] = []
    for fp in fingerprints:
        if fp and fp in norm_out:
            covered += 1
        else:
            missing.append(fp)

    docx_table_rows = sum(len(el.tr_lst) for el in doc.element.body if el.tag == qn("w:tbl"))
    md_table_rows = 0
    for _, lines in outputs:
        for ln in lines:
            if ln.startswith("| ") and not re.match(r"^\|\s*---", ln):
                md_table_rows += 1
    docx_tables = sum(1 for el in doc.element.body if el.tag == qn("w:tbl"))
    md_tables = sum(
        1 for _, lines in outputs for i, ln in enumerate(lines)
        if ln.startswith("| ") and i + 1 < len(lines) and re.match(r"^\|\s*---", lines[i + 1])
    )

    print("=== 转换统计 ===")
    print("读取段落数：%d（其中非空 %d）" % (len(all_paras), len(fingerprints)))
    if skipped_title:
        print("封面标题 %d 段（%s…）有意不进章节正文, 已从核对范围里显式排除"
              % (skipped_title, title_text[:16]))
    print("转换后行数：%d" % total_lines)
    print("表格数：DOCX %d 张 -> Markdown %d 张" % (docx_tables, md_tables))
    print("图片数：%d（输出到 %s/）" % (image_count, args.images_subdir))
    print("输出文件：%d 个" % len(written))
    for path in written:
        print("  - %s（%d 字节）" % (path.name, path.stat().st_size))
    if copy_note:
        print(copy_note)
    print("=== 零丢失核对 ===")
    print("DOCX 原始段落 %d 个 -> 覆盖 %d 个，缺失 %d 个" % (len(fingerprints), covered, len(missing)))
    print("表格行：DOCX %d 行 -> Markdown %d 行，缺失 %d 行"
          % (docx_table_rows, md_table_rows, docx_table_rows - md_table_rows))
    if missing:
        print("缺失样例（最多 5 条）：")
        for fp in missing[:5]:
            print("  ! %s" % fp)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
