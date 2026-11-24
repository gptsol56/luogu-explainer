# -*- coding: utf-8 -*-
#
# gen_tree.py - 生成 README 里的完整文件树, 并保证它不过期
#
# 用法:
#     python tools/gen_tree.py --write     把文件树写进 README
#     python tools/gen_tree.py --check     只检查 README 里的文件树是不是最新的 (CI 用)
#     python tools/gen_tree.py --selftest  离线自检
#
# 文件树是自动生成的: 加了文件忘了刷新 README, CI 会红。
# 每次改完文件跑一次 --write 就行, 不用手抄目录。

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
README_NAME = 'README.md'
START_MARK = '<!-- tree:start -->'
END_MARK = '<!-- tree:end -->'
ROOT_LABEL = 'luogu-explainer/'

# 每个文件一句话说明。改说明就改这里, 然后跑 --write。
NOTES = {
    '.editorconfig': '行尾与缩进规范',
    '.env.example': '空凭据模板, 照它建 .env',
    '.gitignore': '忽略规则',
    'CONTRIBUTING.md': '分支模型与提交规范',
    'Dockerfile': '容器镜像',
    'docker-compose.yml': '容器编排',
    'LICENSE': '许可证',
    'README.md': '主文档',
    'requirements.txt': 'Python 依赖',
    'luogu_punch.py': '打卡 CLI, 单文件, 自带 --selftest',
    '一键启动.cmd': '双击起本地站点并自动开浏览器',
    '.github/PULL_REQUEST_TEMPLATE.md': 'PR 模板',
    '.github/workflows/ci.yml': 'CI 门禁, 五个作业',
    '.github/workflows/pages.yml': 'Pages 发布',
    'docs/SKILLS-INDEX.md': '技能索引, 附带资料',
    'docs/github-skill-stars.md': '技能星标清单, 附带资料',
    'docs/draft/淳阳项目组学习笔记_第一阶段_GIT_AND_AGENT.docx': '笔记原稿, 唯一真源',
    'docs/images/sample-library.png': '示例题区块截图',
    'docs/images/web-ui.png': '界面截图',
    'docs/source-materials/AI Agent 学习计划.md': '第一天学习计划',
    'docs/source-materials/Git学习笔记-第一天.docx': '第一天原始笔记',
    'docs/source-materials/Git学习笔记-第二天.docx': '第二天原始笔记',
    'docs/source-materials/Git学习笔记-第三天.docx': '第三天原始笔记',
    'docs/source-materials/Git学习笔记-第四天.docx': '第四天原始笔记',
    'docs/source-materials/ecc_dashboard_shot.png': 'ECC 面板截图',
    'docs/source-materials/gh-candidate-audit.json': '技能候选审计',
    'docs/source-materials/gh-picked-audit.json': '技能挑选审计',
    'docs/source-materials/前置学习任务.md': '前置任务书',
    'docs/source-materials/前置学习指南.docx': '前置学习指南',
    'docs/source-materials/新建 文本文档.txt': '终端原始记录',
    'docs/source-materials/笔记改造预览.png': '笔记改造预览',
    'docs/source-materials/笔记第三章_我的想法_预览.png': '第三章预览',
    'docs/source-materials/笔记第三章_提交日记_预览.png': '第三章预览',
    'explainer/__init__.py': '包声明',
    'explainer/luogu_explainer.py': '取题 / 提示词 / 调模型, 自带 --selftest',
    'explainer/prompt_template.json': '提示词唯一真源',
    'explainer/providers.json': '模型厂商预设表, 真源',
    'explainer/samples/P1001.json': '示例题 A+B, 题面加解析',
    'explainer/samples/P1090.json': '示例题 合并果子, 题面加解析',
    'explainer/samples/P1421.json': '示例题 小玉买文具, 题面加解析',
    'explainer/samples/index.json': '示例题清单',
    'notes/01-Git-学习记录.md': '第一章',
    'notes/02-AI-Agent-学习记录.md': '第二章',
    'notes/03-提交日记-洛谷打卡助手.md': '第三章',
    'notes/04-把仓库做成一个完整的整体.md': '第四章',
    'notes/05-拆仓库-公开的站点与私有的笔记.md': '第五章',
    'notes/06-示例题解析库.md': '第六章',
    'notes/images/pic1.png': '笔记内嵌图',
    'notes/images/pic2.png': '笔记内嵌图',
    'notes/images/pic3.png': '笔记内嵌图',
    'scripts/install_task.ps1': '注册 Windows 计划任务',
    'scripts/punch.cmd': '一键跑一次打卡',
    'scripts/serve.cmd': '一键起站点',
    'server/app.py': 'API 代理层加静态站点, 只用标准库',
    'tests/test_luogu_punch.py': '打卡工具单元测试',
    'tools/agent_loop.py': 'Agent 主循环示例',
    'tools/bpe_encode_demo.py': '分词编码演示',
    'tools/build_samples.py': '解析库生成与维护, 自带 --selftest',
    'tools/build_site.py': '静态站点组装, 自带 --selftest',
    'tools/check_assets.py': '模板与题库结构校验',
    'tools/check_health.py': '健康检查返回值校验',
    'tools/check_notes.py': '转换结果零丢失核对',
    'tools/check_notes_sync.py': 'notes 与原稿同步校验',
    'tools/cost_manager.py': '成本统计',
    'tools/demo_agent_loop.py': '主循环演示',
    'tools/demo_cost.py': '成本演示',
    'tools/docx_to_md.py': 'DOCX 转 Markdown',
    'tools/gen_tree.py': '生成并校验 README 的文件树',
    'tools/gh_skill_install.py': '从 GitHub 装技能',
    'tools/github_skill_scan.py': '扫描 GitHub 技能',
    'tools/tidy_skills.py': '整理技能目录',
    'tools/verify_skills.py': '技能校验',
    'tools/agents/kit_demo.py': 'Agent 工具包示例',
    'tools/agents/minimal_mcp_server.py': '最小 MCP 服务端',
    'tools/agents/regex_basics.py': '正则基础',
    'tools/agents/regex_engines.py': '正则引擎对比',
    'tools/agents/run_demo.cmd': '示例的 CMD 入口',
    'tools/agents/schema_lab.py': '结构化输出实验',
    'tools/agents/tokenization_demo.py': '分词实验',
    'tools/agents/tool_contract.py': '工具契约实验',
    'web/app.js': '前端逻辑',
    'web/index.html': '页面骨架',
    'web/style.css': '样式',
}


def collect_paths(repo: Path) -> list[str]:
    """列出仓库里该有的文件: 已跟踪的 + 新加还没提交的, 忽略掉的不要。"""
    try:
        proc = subprocess.run(
            ['git', 'ls-files', '--cached', '--others', '--exclude-standard'],
            cwd=str(repo), capture_output=True, text=True, encoding='utf-8',
        )
        if proc.returncode == 0:
            paths = [p.strip() for p in proc.stdout.splitlines() if p.strip()]
            if paths:
                return sorted(set(paths))
    except OSError:
        pass
    # 兜底: 没装 git 就走文件系统
    paths = []
    skip_dirs = {'.git', '__pycache__', '_site', 'node_modules', '.venv'}
    for root, dirs, files in os.walk(str(repo)):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for name in files:
            rel = os.path.relpath(os.path.join(root, name), str(repo))
            paths.append(rel.replace(os.sep, '/'))
    return sorted(set(paths))


def build_tree(paths: list[str], notes: dict[str, str] | None = None) -> list[str]:
    """把一堆相对路径排成树, 目录在前文件在后, 各自按名字排。"""
    notes = notes or {}
    root: dict = {}
    for path in paths:
        parts = [p for p in path.replace('\\', '/').split('/') if p]
        if not parts:
            continue
        node = root
        for part in parts[:-1]:
            child = node.setdefault(part, {})
            if not isinstance(child, dict):
                break
            node = child
        else:
            node.setdefault(parts[-1], None)

    lines = [ROOT_LABEL]

    def walk(node: dict, prefix: str, path: str) -> None:
        items = sorted(node.items(), key=lambda kv: (not isinstance(kv[1], dict), kv[0].lower()))
        for index, (name, child) in enumerate(items):
            last = index == len(items) - 1
            connector = '└── ' if last else '├── '
            rel = (path + '/' + name).lstrip('/')
            is_dir = isinstance(child, dict)
            line = prefix + connector + name + ('/' if is_dir else '')
            note = notes.get(rel)
            if note:
                line += '   # ' + note
            lines.append(line)
            if isinstance(child, dict):
                walk(child, prefix + ('    ' if last else '│   '), rel)

    walk(root, '', '')
    return lines


def render_block(paths: list[str], notes: dict[str, str] | None = None) -> str:
    body = '\n'.join(build_tree(paths, notes))
    return START_MARK + '\n\n```\n' + body + '\n```\n\n' + END_MARK


def extract_block(text: str) -> str | None:
    start = text.find(START_MARK)
    end = text.find(END_MARK)
    if start < 0 or end < 0 or end < start:
        return None
    return text[start:end + len(END_MARK)]


def replace_block(text: str, block: str) -> str:
    old = extract_block(text)
    if old is None:
        raise ValueError('README 里找不到 ' + START_MARK + ' / ' + END_MARK + ' 标记')
    # 块里的行尾跟着正文走, 不能刷新一次目录就把文件搞成混合行尾
    newline = chr(13) + chr(10) if (chr(13) + chr(10)) in text else chr(10)
    return text.replace(old, block.replace(chr(10), newline), 1)


def read_text_preserving(path: Path) -> str:
    """读文件但不改行尾。Path.read_text 在 3.13 之前没有 newline 参数, 所以自己开。"""
    with open(str(path), 'r', encoding='utf-8', newline='') as handle:
        return handle.read()


def write_text_preserving(path: Path, text: str) -> None:
    """写文件但不改行尾。刷新目录不该顺手把整个文件换成另一种行尾。"""
    with open(str(path), 'w', encoding='utf-8', newline='') as handle:
        handle.write(text)


def normalize(text: str) -> str:
    return text.replace('\r\n', '\n').strip()


def diff_lines(old: str, new: str) -> tuple[list[str], list[str]]:
    old_set = set(normalize(old).splitlines())
    new_set = set(normalize(new).splitlines())
    added = sorted(line for line in new_set - old_set)
    removed = sorted(line for line in old_set - new_set)
    return added, removed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='生成 README 的完整文件树')
    parser.add_argument('--write', action='store_true', help='把文件树写进 README')
    parser.add_argument('--check', action='store_true', help='检查 README 里的文件树是不是最新的')
    parser.add_argument('--selftest', action='store_true', help='离线自检')
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    repo = REPO_ROOT
    readme = repo / README_NAME
    paths = collect_paths(repo)
    block = render_block(paths, NOTES)

    if args.check:
        if not readme.is_file():
            print('[FAIL] 找不到 ' + str(readme), file=sys.stderr)
            return 1
        text = read_text_preserving(readme)
        current = extract_block(text)
        if current is None:
            print('[FAIL] README 里没有文件树标记, 跑 python tools/gen_tree.py --write', file=sys.stderr)
            return 1
        if normalize(current) == normalize(block):
            print('README 文件树是最新的: ' + str(len(paths)) + ' 个文件')
            return 0
        added, removed = diff_lines(current, block)
        print('[FAIL] README 里的文件树过期了, 跑 python tools/gen_tree.py --write', file=sys.stderr)
        for line in removed:
            print('  - ' + line, file=sys.stderr)
        for line in added:
            print('  + ' + line, file=sys.stderr)
        return 1

    if args.write:
        if not readme.is_file():
            print('[FAIL] 找不到 ' + str(readme), file=sys.stderr)
            return 1
        text = read_text_preserving(readme)
        try:
            new_text = replace_block(text, block)
        except ValueError as exc:
            print('[FAIL] ' + str(exc), file=sys.stderr)
            return 1
        write_text_preserving(readme, new_text)
        print('README 文件树已刷新: ' + str(len(paths)) + ' 个文件')
        return 0

    print(build_tree(paths, NOTES)[0])
    print('用法: --write 写进 README / --check 只检查 / --selftest 离线自检')
    return 0


def selftest() -> int:
    passed = 0
    failed = 0

    def check(name: str, condition: bool, detail: str = '') -> None:
        nonlocal passed, failed
        if condition:
            passed += 1
            print('  [PASS] ' + name)
        else:
            failed += 1
            print('  [FAIL] ' + name + ((' -> ' + detail) if detail else ''))

    sample = ['a/b.txt', 'a/c/d.md', 'e.py', 'a/b.txt']
    tree = build_tree(sample, {'e.py': '一个文件'})
    joined = chr(10).join(tree)

    def line_of(keyword: str) -> str:
        for line in tree:
            if keyword in line:
                return line
        return ''

    check('根节点在第一行', tree[0] == ROOT_LABEL)
    check('目录排在文件前面', tree.index('├── a/') < tree.index(line_of('e.py')))
    check('目录名带斜杠', '├── a/' in joined and '├── c/' in joined)
    check('目录下面用缩进表示层级', '│   └── b.txt' in joined)
    check('说明挂在文件后面', '一个文件' in line_of('e.py'))
    check('重复路径只算一次', joined.count('b.txt') == 1)

    block = render_block(['x.py'], {})
    check('块里有起止标记', block.startswith(START_MARK) and block.rstrip().endswith(END_MARK))

    with tempfile.TemporaryDirectory() as tmp:
        tmp_readme = Path(tmp) / README_NAME
        tmp_readme.write_text('前言\n\n' + block + '\n\n后记\n', encoding='utf-8')
        text = tmp_readme.read_text(encoding='utf-8')
        check('能从 README 里取出块', extract_block(text) is not None)
        new_block = render_block(['x.py', 'y.py'], {})
        replaced = replace_block(text, new_block)
        check('替换后仍只有一段块', replaced.count(START_MARK) == 1 and replaced.count(END_MARK) == 1)
        check('替换后前言后记还在', '前言' in replaced and '后记' in replaced)
        check('能看出内容变了', normalize(extract_block(replaced) or '') != normalize(block))
        try:
            replace_block('没有标记的文本', new_block)
            check('缺标记时报错', False)
        except ValueError:
            check('缺标记时报错', True)

    with tempfile.TemporaryDirectory() as tmp:
        crlf_readme = Path(tmp) / README_NAME
        crlf_block = block.replace(chr(10), chr(13) + chr(10))
        crlf_readme.write_bytes(('前言' + chr(13) + chr(10) + crlf_block + chr(13) + chr(10) + '后记' + chr(13) + chr(10)).encode('utf-8'))
        kept = read_text_preserving(crlf_readme)
        write_text_preserving(crlf_readme, replace_block(kept, block))
        raw = crlf_readme.read_bytes()
        check('刷新目录不改行尾', raw.count(b'\r\n') >= 2 and b'\n' not in raw.replace(b'\r\n', b''))

    real = collect_paths(REPO_ROOT)
    check('能列出仓库文件', len(real) > 20, '只列出 ' + str(len(real)) + ' 个')
    check('文件清单里有 README', README_NAME in real)

    print('----------------------------------------------')
    print('自检结果: ' + str(passed) + ' passed / ' + str(failed) + ' failed')
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
