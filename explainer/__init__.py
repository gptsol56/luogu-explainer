# -*- coding: utf-8 -*-
"""explainer 包: 洛谷题目自动讲解核心库。

既可以直接当脚本跑:
    python explainer/luogu_explainer.py --selftest
也可以当模块导入:
    from explainer import luogu_explainer
"""

from .luogu_explainer import (  # noqa: F401
    ExplainerError,
    build_prompt,
    call_minimax,
    classify_target,
    config_snapshot,
    explain,
    fetch_problem,
    resolve_config,
    strip_html,
)

__all__ = [
    "ExplainerError",
    "build_prompt",
    "call_minimax",
    "classify_target",
    "config_snapshot",
    "explain",
    "fetch_problem",
    "resolve_config",
    "strip_html",
]
