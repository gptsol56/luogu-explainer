# -*- coding: utf-8 -*-
#
# build_samples.py - 生成并维护示例题解析库
#
# 用途:
#   1. 读 explainer/samples/ 下的样本 (题面 + 讲解), 给缺讲解的样本补一份真调用生成的解析;
#   2. 重建 explainer/samples/index.json (页面用它列出所有示例题);
#   3. 自带 --selftest, 完全离线 (不联网、不读注册表密钥、不需要洛谷账号)。
#
# 样本文件 (explainer/samples/<ID>.json) 的字段:
#   id / pid / title / difficulty / summary  题目身份与一句话说明
#   problem                                 题面纯文本 (抓自洛谷页面)
#   markdown                                讲解正文 (真调模型生成)
#   meta                                    生成信息: provider/model/style/elapsed_ms/tokens/时间
#
# 加一道新题的做法:
#   1. 抓题面, 写一个只含 id/pid/title/difficulty/summary/problem 的 JSON;
#   2. python tools/build_samples.py --only <ID>    # 补齐 markdown, 这一步会真的调模型
#   3. 连同重建后的 index.json 一起提交。
#
# 设计原则 (与仓库里其它工具一致):
#   - 密钥只从环境变量读, 任何出现在错误信息里的密钥都会被抹掉;
#   - 自检离线可跑, 适合放进 CI;
#   - 写文件先写临时文件再改名, 中断不会留下半份 JSON。
#
# 用法:
#   python tools/build_samples.py
#   python tools/build_samples.py --provider deepseek
#   python tools/build_samples.py --only P1421
#   python tools/build_samples.py --force
#   python tools/build_samples.py --selftest

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = REPO_ROOT / 'explainer' / 'samples'
INDEX_NAME = 'index.json'
CST = timezone(timedelta(hours=8))

sys.path.insert(0, str(REPO_ROOT))

from explainer import luogu_explainer as core  # noqa: E402


class BuildError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(CST).replace(microsecond=0).isoformat()


def sample_files(samples_dir: Path) -> list[Path]:
    if not samples_dir.is_dir():
        return []
    return sorted(p for p in samples_dir.glob('*.json') if p.name != INDEX_NAME)


def load_sample(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except ValueError as exc:
        raise BuildError(path.name + ' 不是合法 JSON: ' + str(exc)) from exc
    if not isinstance(data, dict):
        raise BuildError(path.name + ' 顶层不是对象')
    return data


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + '\n'
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + '.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(text)
        os.replace(tmp_name, str(path))
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def build_index(samples: list[dict[str, Any]]) -> dict[str, Any]:
    entries = []
    for spec in samples:
        meta = spec.get('meta') or {}
        entries.append({
            'id': str(spec.get('id') or ''),
            'pid': str(spec.get('pid') or spec.get('id') or ''),
            'title': str(spec.get('title') or ''),
            'difficulty': str(spec.get('difficulty') or ''),
            'summary': str(spec.get('summary') or ''),
            'file': str(spec.get('_file') or (str(spec.get('id') or '') + '.json')),
            'model': str(meta.get('model') or ''),
            'provider': str(meta.get('provider') or ''),
            'generated_at': str(meta.get('generated_at') or ''),
        })
    return {
        'version': '1.0.0',
        'generated_at': now_iso(),
        'samples': entries,
    }


def check_sample(spec: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    for field in ('id', 'title', 'problem'):
        if not str(spec.get(field) or '').strip():
            problems.append('缺少字段 ' + field)
    markdown = str(spec.get('markdown') or '').strip()
    if markdown and '## 题目在考什么' not in markdown:
        problems.append('markdown 缺少第一个小节 (## 题目在考什么)')
    return problems


def generate(spec: dict[str, Any], provider: str, style: str,
              caller: Optional[Callable[..., tuple[str, dict[str, Any]]]] = None) -> dict[str, Any]:
    problem_text = str(spec.get('problem') or '').strip()
    if not problem_text:
        raise BuildError(str(spec.get('id')) + ' 没有题面 (problem 字段为空)')
    prompt = core.build_prompt(problem_text, style)
    call = caller or core.call_model
    if caller is not None:
        # 自检注入的假调用: 不去读真实凭据, 免得自检意外用掉额度
        cfg = {'provider': provider, 'model': 'fake-model', 'api_key': '',
               'base_url': '', 'protocol': 'anthropic'}
    else:
        cfg = core.resolve_config(provider=provider)
    started = time.time()
    markdown, usage = call(prompt, cfg, 180)
    elapsed = int((time.time() - started) * 1000)
    out = dict(spec)
    out.pop('_file', None)
    out['markdown'] = str(markdown).strip()
    meta = dict(spec.get('meta') or {})
    meta.update({
        'provider': str(cfg.get('provider') or provider or ''),
        'model': str(cfg.get('model') or ''),
        'style': style,
        'elapsed_ms': elapsed,
        'input_tokens': usage.get('input_tokens'),
        'output_tokens': usage.get('output_tokens'),
        'total_tokens': usage.get('total_tokens'),
        'generated_at': now_iso(),
    })
    out['meta'] = meta
    return out


def rebuild_index(samples_dir: Path) -> dict[str, Any]:
    specs = []
    for path in sample_files(samples_dir):
        spec = load_sample(path)
        problems = check_sample(spec)
        if problems:
            raise BuildError(path.name + ': ' + '; '.join(problems))
        spec['_file'] = path.name
        specs.append(spec)
    index = build_index(specs)
    write_json_atomic(samples_dir / INDEX_NAME, index)
    return index


def run_generate(samples_dir: Path, provider: str, style: str, only: Optional[str],
                 force: bool, caller: Optional[Callable[..., tuple[str, dict[str, Any]]]] = None,
                 printer: Callable[[str], None] = print) -> dict[str, Any]:
    if not samples_dir.is_dir():
        raise BuildError('找不到样本目录: ' + str(samples_dir))
    done = []
    skipped = []
    for path in sample_files(samples_dir):
        spec = load_sample(path)
        sid = str(spec.get('id') or path.stem)
        if only and sid.upper() != only.upper():
            skipped.append(sid)
            continue
        if str(spec.get('markdown') or '').strip() and not force:
            skipped.append(sid)
            continue
        printer('生成 ' + sid + ' ...')
        updated = generate(spec, provider, style, caller=caller)
        write_json_atomic(path, updated)
        done.append(sid)
    index = rebuild_index(samples_dir)
    return {'generated': done, 'skipped': skipped, 'index': index}
def _fake_caller(prompt: str, cfg: dict[str, str], timeout: int = 0) -> tuple[str, dict[str, Any]]:
    # 自检用的假调用: 断言调用时手上没有真实密钥
    assert not str(cfg.get('api_key') or ''), '自检不该拿到真实密钥'
    assert '## 题目在考什么' in prompt, 'prompt 里应该有固定小节'
    return ('## 题目在考什么\n\n假内容。\n',
            {'input_tokens': 1, 'output_tokens': 2, 'total_tokens': 3})


class _NoSecret:
    # 把凭据回退的每一级都换掉: 环境变量 + 注册表
    def __enter__(self) -> '_NoSecret':
        self.saved_env = {}
        for key in list(os.environ):
            if key.endswith('_API_KEY'):
                self.saved_env[key] = os.environ.pop(key)
        self.saved_reader = core._read_registry_env
        core._read_registry_env = lambda: {}
        return self

    def __exit__(self, *exc: Any) -> None:
        core._read_registry_env = self.saved_reader
        for key, value in self.saved_env.items():
            os.environ[key] = value


def _make_sample_dir(tmp: Path) -> Path:
    d = tmp / 'samples'
    d.mkdir(parents=True, exist_ok=True)
    base = {
        'id': 'P9999',
        'pid': 'P9999',
        'title': '测试题',
        'difficulty': '入门',
        'summary': '给自检用',
        'problem': '题目描述\n\n这是一道给自检用的题。\n',
    }
    (d / 'P9999.json').write_text(json.dumps(base, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    done = dict(base)
    done['id'] = 'P8888'
    done['pid'] = 'P8888'
    done['markdown'] = '## 题目在考什么\n\n已有解析。\n'
    done['meta'] = {'model': 'fake', 'provider': 'fake', 'generated_at': '2026-01-01T00:00:00+08:00'}
    (d / 'P8888.json').write_text(json.dumps(done, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return d


def _selftest() -> int:
    cases: list[tuple[str, Callable[[], None]]] = []

    def case(name: str):
        def deco(fn: Callable[[], None]) -> Callable[[], None]:
            cases.append((name, fn))
            return fn
        return deco

    @case('样本目录里的文件都能解析, 字段齐全')
    def _() -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            d = _make_sample_dir(Path(tmp))
            for path in sample_files(d):
                spec = load_sample(path)
                problems = check_sample(spec)
                assert not problems, (path.name, problems)

    @case('缺解析的样本会被补齐, 已有解析的跳过')
    def _() -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            d = _make_sample_dir(Path(tmp))
            with _NoSecret():
                info = run_generate(d, 'minimax', '面向初学者', None, False,
                                    caller=_fake_caller, printer=lambda s: None)
            assert info['generated'] == ['P9999'], info['generated']
            assert 'P8888' in info['skipped'], info['skipped']
            spec = load_sample(d / 'P9999.json')
            assert '## 题目在考什么' in spec['markdown'], spec['markdown']
            assert spec['meta']['model'], spec['meta']

    @case('--force 会重新生成已有的解析')
    def _() -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            d = _make_sample_dir(Path(tmp))
            with _NoSecret():
                info = run_generate(d, 'minimax', '面向初学者', None, True,
                                    caller=_fake_caller, printer=lambda s: None)
            assert sorted(info['generated']) == ['P8888', 'P9999'], info['generated']

    @case('--only 只处理指定的题')
    def _() -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            d = _make_sample_dir(Path(tmp))
            with _NoSecret():
                info = run_generate(d, 'minimax', '面向初学者', 'P9999', False,
                                    caller=_fake_caller, printer=lambda s: None)
            assert info['generated'] == ['P9999'], info['generated']

    @case('index.json 能从样本目录重建')
    def _() -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            d = _make_sample_dir(Path(tmp))
            index = rebuild_index(d)
            ids = sorted(e['id'] for e in index['samples'])
            assert ids == ['P8888', 'P9999'], ids
            for entry in index['samples']:
                assert (d / entry['file']).is_file(), entry
            saved = json.loads((d / INDEX_NAME).read_text(encoding='utf-8'))
            assert saved['samples'], saved

    @case('没有密钥时生成会失败, 且错误信息不含密钥')
    def _() -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            d = _make_sample_dir(Path(tmp))
            with _NoSecret():
                try:
                    cfg = core.resolve_config(provider='minimax')
                except core.ExplainerError as exc:
                    # 没有密钥时 resolve_config 自己就会拦下来
                    assert 'API Key' in str(exc), str(exc)
                    return
                assert not str(cfg.get('api_key') or ''), '自检环境里不该有密钥'
                try:
                    core.call_model('测试用的 prompt', cfg, 5)
                except core.ExplainerError as exc:
                    assert 'API Key' in str(exc), str(exc)
                else:
                    raise AssertionError('没有密钥时应该报错')

    @case('坏 JSON 能被检出')
    def _() -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            d = _make_sample_dir(Path(tmp))
            (d / 'bad.json').write_text('{ not json', encoding='utf-8')
            try:
                load_sample(d / 'bad.json')
            except BuildError as exc:
                assert '不是合法 JSON' in str(exc), str(exc)
            else:
                raise AssertionError('坏 JSON 应该被检出')

    @case('仓库里的样本目录存在且有清单')
    def _() -> None:
        assert SAMPLES_DIR.is_dir(), SAMPLES_DIR
        files = sample_files(SAMPLES_DIR)
        assert files, '样本目录里应该有题'
        index_path = SAMPLES_DIR / INDEX_NAME
        assert index_path.is_file(), index_path
        index = json.loads(index_path.read_text(encoding='utf-8'))
        assert index.get('samples'), index
        for entry in index['samples']:
            assert (SAMPLES_DIR / entry['file']).is_file(), entry

    passed = 0
    failed = 0
    print('示例题解析库 离线自检')
    print('-' * 46)
    for name, fn in cases:
        try:
            fn()
        except AssertionError as exc:
            failed += 1
            print('  [FAIL] ' + name + ': ' + str(exc))
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print('  [ERROR] ' + name + ': ' + type(exc).__name__ + ': ' + str(exc))
        else:
            passed += 1
            print('  [PASS] ' + name)
    print('-' * 46)
    print('自检结果: ' + str(passed) + ' passed / ' + str(failed) + ' failed')
    return 0 if failed == 0 else 1


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description='生成并维护示例题解析库')
    ap.add_argument('--provider', default='minimax', help='用哪家模型生成, 默认 minimax')
    ap.add_argument('--style', default='面向初学者', help='讲解风格, 默认 面向初学者')
    ap.add_argument('--only', help='只处理某一道题 (按 id)')
    ap.add_argument('--force', action='store_true', help='已有的解析也重新生成')
    ap.add_argument('--index-only', action='store_true', help='只重建 index.json, 不调模型')
    ap.add_argument('--selftest', action='store_true', help='离线自检, 不联网')
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    try:
        if args.index_only:
            index = rebuild_index(SAMPLES_DIR)
            print('index.json 已重建, 共 ' + str(len(index['samples'])) + ' 道示例题')
            return 0
        info = run_generate(SAMPLES_DIR, args.provider, args.style, args.only, args.force)
    except (BuildError, core.ExplainerError) as exc:
        print('[失败] ' + str(exc), file=sys.stderr)
        return 1
    print('新生成 ' + str(len(info['generated'])) + ' 道: ' + (', '.join(info['generated']) or '-'))
    print('跳过 ' + str(len(info['skipped'])) + ' 道: ' + (', '.join(info['skipped']) or '-'))
    print('index.json 已重建, 共 ' + str(len(info['index']['samples'])) + ' 道示例题')
    return 0


if __name__ == '__main__':
    sys.exit(main())
