# -*- coding: utf-8 -*-
import sys, time
sys.stdout.reconfigure(encoding='utf-8')
import re as pyre          # Python 内置：回溯引擎
import regex as rxre       # PyPI regex：绑定 Rust regex crate，有限自动机
import tiktoken

SEP = "=" * 78
def show(t=""): print(t)

# ===============================================================
show(SEP); show("1. 基本构件速查"); show(SEP)
cases = [
    ("字面量",      r"abc",           ["abc", "xabcx", "ab c"]),
    ("字符类 []",   r"[0-9a-f]",       ["a", "7", "g", "Z"]),
    ("否定类 [^]",  r"[^\s]",         ["a", " ", "\t"]),
    ("量词 ?",      r"colou?r",       ["color", "colour"]),
    ("量词 *",      r"ab*c",          ["ac", "abbc"]),
    ("量词 +",      r"ab+c",          ["ac", "abbc"]),
    ("量词 {m,n}",  r"a{2,3}",        ["a", "aa", "aaa", "aaaa"]),
    ("分组 ()",     r"(ab)+",         ["abab", "ababab", "ab"]),
    ("或 |",        r"cat|dog",       ["cat", "dog", "cow"]),
    ("锚点 ^ $",    r"^ab$",          ["ab", "xab", "abx"]),
]
for name, pat, tests in cases:
    show(f"  {name:12s} /{pat}/")
    for t in tests:
        m = pyre.fullmatch(pat, t) if name != "字面量" else pyre.fullmatch(pat, t)
        show(f"      {t!r:12s} -> {'匹配' if m else '不匹配'}")
    show()

# ===============================================================
show(SEP); show("2. Unicode 属性：\\p{L} / \\p{N} 是啥"); show(SEP)
for label, pat in [("\\p{L} 字母", r"\p{L}"), ("\\p{N} 数字", r"\p{N}"),
                   ("\\p{Lu} 大写", r"\p{Lu}"), ("\\p{Ll} 小写", r"\p{Ll}")]:
    show(f"  {label:16s} '汉'={bool(rxre.fullmatch(pat,'汉'))}  "
         f"'a'={bool(rxre.fullmatch(pat,'a'))}  "
         f"'A'={bool(rxre.fullmatch(pat,'A'))}  "
         f"'5'={bool(rxre.fullmatch(pat,'5'))}")
show()
show("  => \\p{L} 包含 汉字/假名/希腊/西里尔; \\p{N} 是数字。")
show("     这是 GPT-4o 代(o200k)用 \\p{Lu}\\p{Lt}\\p{Lm}\\p{Lo}\\p{M} 细分大小写的原因。")
show()

# ===============================================================
show(SEP); show("3. 贪婪 / 惰性 / possessive（占有型不回溯）"); show(SEP)
for label, pat in [("贪婪 +", r"<.+>"), ("惰性 +?", r"<.+?>"),
                   ("占有 ++", r"<.++>")]:
    show(f"  {label:12s} /{pat}/  匹配 '<a><b>' -> {rxre.findall(pat,'<a><b>')}")
show()
show("  占有型量词 ++ ?+ *+ 与原子组 (?>...): 匹配后【不回溯】。")
show("  最能说明问题的一组 —— 同一段文本, 两种引擎结果不同:")
show(f"    /(a|ab)c/         'abc' -> {rxre.findall(r'(a|ab)c','abc')}   (贪心, 回溯成功)")
show(f"    /(?:(a|ab)++)c/   'abc' -> {rxre.findall(r'(?:(a|ab)++)c','abc')}   (占有型, 不回溯, 失败)")
show()
show("  支持情况:")
show(f"    Python 3.11+ 内置 re : {bool(pyre.fullmatch(r'a++','aaa'))}")
show(f"    PyPI regex 模块      : {bool(rxre.fullmatch(r'a++','aaa'))}")
show(f"    Python 3.10 及以前  : 不支持 (本机是 {sys.version_info.major}.{sys.version_info.minor})")
show("    JavaScript           : 不支持")
show()

# ===============================================================
show(SEP); show("4. 拆解 cl100k_base 的预分词正则（逐分支）"); show(SEP)
enc = tiktoken.get_encoding("cl100k_base")
FULL = enc._pat_str
show(f"  {FULL}")
show()
branches = [
    ("(?i:[sdmt]|ll|ve|re)",              "英文缩写: 's 't 're 've 'm 'll 'd"),
    (r"[^\r\n\p{L}\p{N}]?+\p{L}++",   "可选前缀(非字母数字) + 一串字母"),
    (r"\p{N}{1,3}+",                      "数字, 按 1~3 位一组"),
    (r" ?[^\s\p{L}\p{N}]++[\r\n]*+",    "可选空格 + 一串符号 + 尾随换行"),
    (r"\s++$",                            "行尾空白(占有型)"),
    (r"\s*[\r\n]",                       "空白 + 换行"),
    (r"\s+(?!\S)",                        "一串空白, 后面不跟非空白"),
    (r"\s",                               "单个空白"),
]
for pat, desc in branches:
    show(f"  {pat}")
    show(f"      {desc}")
show()
show("  实际预分词效果 (Python regex 模块, 与 tiktoken 同源):")
PAT = rxre.compile(FULL)
for s in ["Hello world, 你好 world!", "don't  it's  3.14159",
          "def f(x):\n    return x", "  indented", "New York"]:
    show(f"    {s!r:34s} -> {PAT.findall(s)}")
show()

# ===============================================================
show(SEP); show("5. 引擎差异: 回溯 vs 有限自动机（灾难性回溯）"); show(SEP)
evil = "a" * 24 + "X"
p = r"(a+)+$"
show(f"  病态输入: {p!r}  vs  {evil[:10]}...a*24 + 'X'")
t0 = time.time()
try:
    pyre.match(p, evil)
    py = f"{time.time()-t0:.3f}s"
except Exception as e:
    py = f"异常 {type(e).__name__}"
t0 = time.time()
rxre.match(p, evil)
rx = f"{time.time()-t0:.6f}s"
show(f"    Python 内置 re (回溯): {py}")
show(f"    regex 模块 (Rust 自动机): {rx}")
show("    -> 回溯引擎在失败匹配上指数爆炸; 有限自动机保证线性时间。")
show()

# ===============================================================
show(SEP); show("6. 常见坑"); show(SEP)
show("  坑1: 贪婪 '.*' 吞太多")
show(f"    /<.+>/   匹配 '<a><b>' -> {rxre.findall(r'<.+>','<a><b>')}")
show(f"    /<.+?>/  匹配 '<a><b>' -> {rxre.findall(r'<.+?>','<a><b>')}")
show("  坑2: . 默认不匹配换行, 要跨行用 re.DOTALL / (?s)")
show(f"    /a.b/ 匹配 'a\nb' -> {bool(rxre.fullmatch(r'a.b','a\nb'))}")
show(f"    /a(?s).b/ 匹配 'a\nb' -> {bool(rxre.fullmatch(r'a(?s).b','a\nb'))}")
show("  坑3: 捕获组会改变 group 编号, 非捕获组 (?: ) 更稳")
show("  坑4: Python 内置 re 不认 \\p{L}, 直接抛异常; 要用 regex 模块 (本轮装的)")
try:
    v = bool(pyre.fullmatch(r'\p{L}','汉'))
    show(f"    re.fullmatch(r'\\p{{L}}','汉') -> {v}")
except Exception as e:
    show(f"    re.fullmatch(r'\\p{{L}}','汉') -> 抛出 {type(e).__name__}: {e}")
show(f"    regex.fullmatch(r'\\p{{L}}','汉') -> {bool(rxre.fullmatch(r'\p{L}','汉'))}")
show("  坑5: 环视(lookaround) Rust regex 支持, 但不支持反向引用(backreference)")
show(f"    regex 支持 (?!x): {bool(rxre.match(r'a(?!b)','ac'))}")
show(f"    regex 支持 (?<=a)b: {bool(rxre.match(r'(?<=a)b','ab'))}")
