# -*- coding: utf-8 -*-
#
# check_assets.py - 校验提示词模板与示例题库这两个静态资源
#
# 用法:
#     python tools/check_assets.py <tpl.json> <samples_dir>
#
# samples_dir 是示例题库目录, 里面要有 index.json (清单) 与每道题的 JSON。

from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED_SECTIONS = ('题目在考什么', '思路推导', '关键代码', '复杂度', '常见坑', '自测题')


def check_template(path: Path) -> list[str]:
    problems: list[str] = []
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        return ['提示词模板读取失败: ' + str(exc)]
    if not isinstance(data, dict):
        return ['提示词模板不是 JSON 对象']
    sections = data.get('required_sections')
    if not isinstance(sections, list) or len(sections) < 6:
        problems.append('required_sections 少于 6 个小节')
    template = str(data.get('user_prompt_template') or '')
    for marker in ('{{style}}', '{{sections}}', '{{problem}}'):
        if marker not in template:
            problems.append('模板缺少占位符 ' + marker)
    styles = data.get('styles')
    if not isinstance(styles, list) or not styles:
        problems.append('styles 为空')
    return problems


def check_examples(directory: Path) -> list[str]:
    problems: list[str] = []
    index_path = directory / 'index.json'
    if not index_path.is_file():
        return ['示例题清单不存在: ' + str(index_path)]
    try:
        index = json.loads(index_path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        return ['示例题清单读取失败: ' + str(exc)]
    if not isinstance(index, dict):
        return ['示例题清单不是 JSON 对象']
    samples = index.get('samples')
    if not isinstance(samples, list) or not samples:
        return ['示例题清单里没有 samples']
    for entry in samples:
        if not isinstance(entry, dict):
            problems.append('有一条示例题不是对象')
            continue
        sid = str(entry.get('id') or '')
        name = str(entry.get('file') or '')
        if not sid:
            problems.append('有一条示例题缺少 id')
        if not name:
            problems.append('示例题 ' + sid + ' 缺少 file')
            continue
        path = directory / name
        if not path.is_file():
            problems.append('示例题文件缺失: ' + name)
            continue
        try:
            spec = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            problems.append(name + ' 读取失败: ' + str(exc))
            continue
        markdown = str(spec.get('markdown') or '')
        if len(markdown) < 200:
            problems.append('示例题 ' + sid + ' 正文过短: ' + str(len(markdown)) + ' 字符')
        for section in REQUIRED_SECTIONS:
            if section not in markdown:
                problems.append('示例题 ' + sid + ' 缺少小节: ' + section)
        if not str(spec.get('problem') or '').strip():
            problems.append('示例题 ' + sid + ' 没有题面')
        meta = spec.get('meta') or {}
        if not isinstance(meta, dict):
            problems.append('示例题 ' + sid + ' 的 meta 不是对象')
            continue
        for field in ('provider', 'model', 'generated_at'):
            if not str(meta.get(field) or '').strip():
                problems.append('示例题 ' + sid + ' 的 meta 缺少 ' + field)
    return problems


def main(argv=None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if len(args) < 2:
        print('用法: python tools/check_assets.py <tpl.json> <samples_dir>', file=sys.stderr)
        return 2
    problems: list[str] = []
    problems += check_template(Path(args[0]))
    problems += check_examples(Path(args[1]))
    if problems:
        print('[FAIL] 静态资源校验未通过:', file=sys.stderr)
        for item in problems:
            print('  - ' + item, file=sys.stderr)
        return 1
    print('静态资源校验通过: 模板小节齐全, 示例题库每道题都有题面与全部固定小节')
    return 0


if __name__ == '__main__':
    sys.exit(main())
