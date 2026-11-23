# -*- coding: utf-8 -*-
import sys, time, importlib.util
sys.stdout.reconfigure(encoding='utf-8')
import re as pyre
import regex as rxre

def show(t=""): print(t)

show("=" * 70)
show("1. tiktoken 用的是 Rust 扩展还是纯 Python?")
show(f"   tiktoken._tiktoken 是否存在: {importlib.util.find_spec('tiktoken._tiktoken') is not None}")
import tiktoken
enc = tiktoken.get_encoding("cl100k_base")
show(f"   Encoding.__module__ = {type(enc).__module__}")
show(f"   底层 core_bpe 类型   = {type(enc._core_bpe).__name__}")
show()

show("=" * 70)
show("2. 灾难性回溯 (a+)+$ 在不同引擎/长度下的耗时")
show(f"   {'n(a)':>6}  {'Python re':>14}  {'regex模块':>14}")
p = r"(a+)+$"
for n in [18, 22, 24, 26, 28]:
    evil = "a" * n + "X"
    t0 = time.time()
    try:
        pyre.match(p, evil)
        py = f"{time.time()-t0:.4f}s"
    except Exception:
        py = "err"
    t0 = time.time()
    rxre.match(p, evil)
    rx = f"{time.time()-t0:.6f}s"
    show(f"   {n:>6}  {py:>14}  {rx:>14}")
show()
show("   Python re 每多 2 个 a 约 4 倍 -> 指数爆炸 (回溯引擎)")
show("   regex 模块增长极缓 -> 它对嵌套量词做了优化, 不是纯回溯")
show()

show("=" * 70)
show("3. 语法特性支持矩阵")
feat = [
    ("\\p{L} Unicode属性", r"\p{L}",        "汉"),
    ("占有量词 ++",          r"a++",          "aaa"),
    ("原子组 (?>...)",       r"(?>a+)b",      "aab"),
    ("环视 前瞻 (?!x)",       r"a(?!b)",       "ac"),
    ("环视 后顾 (?<=x)",      r"(?<=a)b",      "ab"),
    ("反向引用 (a)\\1",      r"(a)\1",       "aa"),
    ("命名组 (?P<n>..)",     r"(?P<x>[a-z]+)", "abc"),
    ("递归 (?&name)",        r"(?P<a>a(?&a)?)", "aa"),
]
show(f"   {'特性':<24} {'Python re':>10}  {'regex模块':>10}")
for name, pat, s in feat:
    def t(engine):
        try:
            return "支持" if engine.fullmatch(pat, s) else "语法OK/未匹配"
        except Exception as e:
            return "不支持"
    show(f"   {name:<24} {t(pyre):>10}  {t(rxre):>10}")
