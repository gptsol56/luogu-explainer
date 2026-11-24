# -*- coding: utf-8 -*-
"""
build_site.py - 把静态站点组装成可发布的目录

用途:
  1. GitHub Pages 部署前把 web/ 与提示词模板组装成 _site/;
  2. CI 冒烟测试用同一个脚本组装, 保证「测的」和「发的」是同一份东西。

设计原则 (与仓库根的 luogu_punch.py 一致):
  - 只做确定性的文件复制 + 校验, 不联网、不需要任何凭据;
  - 自带 --selftest, 完全离线;
  - 产物目录先建临时目录再原子改名, 中断不会留下半份站点。

用法:
    python tools/build_site.py --out _site
    python tools/build_site.py --selftest
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Callable, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = REPO_ROOT / "web"
TEMPLATE_PATH = REPO_ROOT / "explainer" / "prompt_template.json"
PROVIDERS_PATH = REPO_ROOT / "explainer" / "providers.json"

# 发布产物里必须存在的文件
REQUIRED_FILES = (
    "index.html",
    "app.js",
    "style.css",
    "sample-explanation.json",
    "prompt_template.json",
    "providers.json",
)

# 静态产物里绝对不该出现的东西 (密钥 / 真实 cookie / 私有域名)
FORBIDDEN_PATTERNS = (
    "MINIMAX_API_KEY=",
    "LUOGU_CLIENT_ID=",
    "LUOGU_UID=",
    "__client_id=",
    "x-api-key: ",
    "anthropic-dangerous-direct-browser-access: true",
)

# 演示样例里允许出现的说明性文字 (避免误报)
ALLOWED_SNIPPETS = (
    "anthropic-dangerous-direct-browser-access",
)

class BuildError(RuntimeError):
    """构建过程中的可预期错误。"""


def _scan_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def collect_files(out_dir: Path) -> list[Path]:
    """列出产物目录里的全部文件。"""
    if not out_dir.is_dir():
        return []
    return [p for p in out_dir.rglob("*") if p.is_file()]


def check_required(out_dir: Path) -> list[str]:
    """检查必需文件是否齐全, 返回缺失清单。"""
    missing: list[str] = []
    for name in REQUIRED_FILES:
        if not (out_dir / name).is_file():
            missing.append(name)
    return missing


def check_secrets(out_dir: Path) -> list[str]:
    """扫描产物里的敏感字面量, 返回命中清单。"""
    hits: list[str] = []
    for path in collect_files(out_dir):
        text = _scan_text(path)
        if not text:
            continue
        for pattern in FORBIDDEN_PATTERNS:
            if pattern in text:
                hits.append(path.name + " :: " + pattern)
    return hits


def check_template(out_dir: Path) -> list[str]:
    """校验产物里的提示词模板能被解析且小节齐全。"""
    problems: list[str] = []
    target = out_dir / "prompt_template.json"
    if not target.is_file():
        return ["prompt_template.json 不存在"]
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except ValueError as exc:
        return ["prompt_template.json 不是合法 JSON: " + str(exc)]
    if not isinstance(data, dict):
        return ["prompt_template.json 不是对象"]
    sections = data.get("required_sections")
    if not isinstance(sections, list) or len(sections) < 6:
        problems.append("required_sections 少于 6 个小节")
    template = str(data.get("user_prompt_template") or "")
    for marker in ("{{style}}", "{{sections}}", "{{problem}}"):
        if marker not in template:
            problems.append("模板缺少占位符 " + marker)
    return problems


def check_providers(out_dir: Path) -> list[str]:
    """校验产物里的模型预设表能被解析, 且每条预设都指向已知协议。"""
    problems: list[str] = []
    target = out_dir / "providers.json"
    if not target.is_file():
        return ["providers.json 不存在"]
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except ValueError as exc:
        return ["providers.json 不是合法 JSON: " + str(exc)]
    if not isinstance(data, dict):
        return ["providers.json 不是对象"]
    protocols = data.get("protocols")
    providers = data.get("providers")
    if not isinstance(protocols, dict) or not protocols:
        problems.append("protocols 缺失或为空")
    if not isinstance(providers, list) or not providers:
        problems.append("providers 缺失或为空")
        return problems
    for spec in providers:
        if not isinstance(spec, dict):
            problems.append("有一条预设不是对象")
            continue
        for field in ("id", "label", "protocol"):
            if not spec.get(field):
                problems.append("预设缺少字段 " + field)
        if isinstance(protocols, dict) and spec.get("protocol") not in protocols:
            problems.append("预设引用了未知协议 " + str(spec.get("protocol")))
    default = str(data.get("default_provider") or "")
    ids = [str(s.get("id")) for s in providers if isinstance(s, dict)]
    if default and default not in ids:
        problems.append("默认厂商不在列表里: " + default)
    return problems


def build(out_dir: Path) -> dict[str, Any]:
    """把 web/ 与提示词模板组装到 out_dir, 并做三项校验。"""
    if not WEB_DIR.is_dir():
        raise BuildError("找不到前端目录: " + str(WEB_DIR))
    if not TEMPLATE_PATH.is_file():
        raise BuildError("找不到提示词模板: " + str(TEMPLATE_PATH))
    if not PROVIDERS_PATH.is_file():
        raise BuildError("找不到模型预设表: " + str(PROVIDERS_PATH))

    out_dir = out_dir.resolve()
    staging = out_dir.parent / (out_dir.name + ".building")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    try:
        for item in sorted(WEB_DIR.iterdir()):
            if item.name.startswith("."):
                continue
            if item.is_dir():
                shutil.copytree(item, staging / item.name)
            else:
                shutil.copy2(item, staging / item.name)
        shutil.copy2(TEMPLATE_PATH, staging / "prompt_template.json")
        shutil.copy2(PROVIDERS_PATH, staging / "providers.json")

        missing = check_required(staging)
        if missing:
            raise BuildError("产物缺少文件: " + ", ".join(missing))
        hits = check_secrets(staging)
        hits = [h for h in hits if not any(a in h for a in ALLOWED_SNIPPETS)]
        if hits:
            raise BuildError("产物里出现敏感字面量: " + "; ".join(hits))
        problems = check_template(staging)
        if problems:
            raise BuildError("产物里的提示词模板有问题: " + "; ".join(problems))
        provider_problems = check_providers(staging)
        if provider_problems:
            raise BuildError("产物里的模型预设表有问题: " + "; ".join(provider_problems))

        if out_dir.exists():
            shutil.rmtree(out_dir)
        staging.rename(out_dir)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise

    files = collect_files(out_dir)
    return {
        "out_dir": str(out_dir),
        "file_count": len(files),
        "total_bytes": sum(p.stat().st_size for p in files),
        "files": sorted(p.name for p in files),
    }


def _selftest() -> int:
    """离线自检: 不联网, 不需要凭据, 产物建在临时目录里。"""
    cases: list[tuple[str, Callable[[], None]]] = []

    def case(name: str):
        def deco(fn: Callable[[], None]) -> Callable[[], None]:
            cases.append((name, fn))
            return fn
        return deco

    @case("web 目录与提示词模板都在")
    def _() -> None:
        assert WEB_DIR.is_dir(), WEB_DIR
        assert TEMPLATE_PATH.is_file(), TEMPLATE_PATH

    @case("组装产物包含全部必需文件")
    def _() -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "site"
            info = build(out)
            assert info["file_count"] >= len(REQUIRED_FILES), info
            for name in REQUIRED_FILES:
                assert (out / name).is_file(), name
            assert not (Path(tmp) / "site.building").exists(), "临时目录应被清理"

    @case("产物里的提示词模板可解析且小节齐全")
    def _() -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "site"
            build(out)
            problems = check_template(out)
            assert not problems, problems

    @case("产物里没有密钥字面量")
    def _() -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "site"
            build(out)
            hits = check_secrets(out)
            hits = [h for h in hits if not any(a in h for a in ALLOWED_SNIPPETS)]
            assert not hits, hits

    @case("产物里的模型预设表可解析且预设齐全")
    def _() -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "site"
            build(out)
            problems = check_providers(out)
            assert not problems, problems

    @case("模型预设表检查能报出缺失")
    def _() -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "site"
            out.mkdir()
            problems = check_providers(out)
            assert problems, problems

    @case("必需文件检查能报出缺失")
    def _() -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "site"
            out.mkdir()
            missing = check_required(out)
            assert "index.html" in missing, missing
            assert len(missing) == len(REQUIRED_FILES), missing

    @case("重复构建会覆盖旧产物")
    def _() -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "site"
            build(out)
            (out / "stale.txt").write_text("x", encoding="utf-8")
            build(out)
            assert not (out / "stale.txt").exists(), "旧产物应被整体替换"

    passed = 0
    failed = 0
    print("静态站点构建 离线自检")
    print("-" * 46)
    for name, fn in cases:
        try:
            fn()
        except AssertionError as exc:
            failed += 1
            print("  [FAIL] " + name + ": " + str(exc))
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("  [ERROR] " + name + ": " + type(exc).__name__ + ": " + str(exc))
        else:
            passed += 1
            print("  [PASS] " + name)
    print("-" * 46)
    print("自检结果: " + str(passed) + " passed / " + str(failed) + " failed")
    return 0 if failed == 0 else 1


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="组装洛谷讲解静态站点")
    ap.add_argument("--out", default="_site", help="产物目录, 默认 _site")
    ap.add_argument("--selftest", action="store_true", help="离线自检, 不联网")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    try:
        info = build(Path(args.out))
    except BuildError as exc:
        print("[构建失败] " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
