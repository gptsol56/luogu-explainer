# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')
import tiktoken
import regex as re

enc  = tiktoken.get_encoding("cl100k_base")
enc2 = tiktoken.get_encoding("o200k_base")
SEP = "=" * 76

def show(t=""):
    print(t)

# GPT-2 的 byte -> 可打印 unicode 映射：让 0-255 全部字节都能进 BPE 词表
def bytes_to_unicode():
    bs = (list(range(ord("!"), ord("~")+1))
          + list(range(ord("\xa1"), ord("\xac")+1))
          + list(range(ord("\xae"), ord("\xff")+1)))
    cs = bs[:]
    n = 0
    for b in range(256):
        if b not in bs:
            bs.append(b); cs.append(256 + n); n += 1
    return dict(zip(bs, [chr(c) for c in cs]))

B2U = bytes_to_unicode()
def visible(raw: bytes) -> str:
    """把 token 的原始字节渲染成模型实际'看到'的字符形态"""
    return "".join(B2U[b] for b in raw)

def tk(e, s):
    return [(i, e.decode_single_token_bytes(i)) for i in e.encode(s)]

# ---------------------------------------------------------------- 1
show(SEP); show("1. TOKEN / CHAR 比率实测 (cl100k_base)"); show(SEP)
samples = [
    ("英文散文",  "The quick brown fox jumps over the lazy dog near the riverbank at dawn."),
    ("中文",      "人工智能代理正在学习如何调用工具并管理上下文窗口的预算与裁剪策略。"),
    ("代码",      "def handler(req, res):\n    return res.json({'ok': True, 'items': req.query.items})\n"),
    ("JSON",      '{"name":"Alice","role":"admin","active":true,"score":98,"tags":[1,2,3]}'),
    ("中英混排",  "请帮我 review 这个 PR 的 code，并给出 performance 建议。"),
    ("emoji",     "\U0001F525\U0001F680\u2705 done \U0001F389"),
]
for name, s in samples:
    ids = enc.encode(s); nb = len(s.encode("utf-8"))
    show(f"{name:9s} chars={len(s):4d} bytes={nb:4d} tokens={len(ids):4d}  "
         f"chars/tok={len(s)/len(ids):5.2f}  bytes/tok={nb/len(ids):5.2f}")

# ---------------------------------------------------------------- 2
show(); show(SEP); show("2. 逐 token 拆解：模型'看到'的到底是什么"); show(SEP)
show("  文本: '智能体会调用工具'")
show(f"  {'id':>6}  {'原始字节':<14} {'模型可见形态':<12} {'可见字节数':>6}")
for i, b in tk(enc, "智能体会调用工具"):
    show(f"  {i:>6}  {b.hex(' '):<14} {visible(b):<14} {len(b):>6}")
show()
show("  关键: '智' 被拆成 2 个字节级 token (e6 99 + ba)，模型从没见到完整的'智'字。")

# ---------------------------------------------------------------- 3
show(); show(SEP); show("3. 字节级兜底：罕见字符如何被拆到字节"); show(SEP)
for ch in ["\u4F60", "\u597D", "\U0001F525", "\U00020BB7", "\u20AC"]:
    b = ch.encode("utf-8")
    ids = enc.encode(ch)
    show(f"  {ch!r:8s} utf8={b.hex(' '):<14}({len(b)}B) -> {len(ids)} token   可见={visible(b)!r}")
    for i, rb in tk(enc, ch):
        show(f"          id={i:<7d} raw={rb.hex(' '):<14} 可见={visible(rb)!r}")

# ---------------------------------------------------------------- 4
show(); show(SEP); show("4. 空格粘词：byte-level BPE 的 'Ġ' 设计"); show(SEP)
for s in [" tokenization", "tokenization", " indentation", "indentation", " hello world"]:
    ids = enc.encode(s)
    show(f"  {s!r:18s} -> {len(ids)} token  {[visible(enc.decode_single_token_bytes(i)) for i in ids]}")
show()
show("  'Ġ' 就是空格(0x20)被映射成的可见字符。空格被吸进词里，所以")
show("  ' indentation' 是 1 个 token，而 'indentation' 单独出现要 2 个。")

# ---------------------------------------------------------------- 5
show(); show(SEP); show("5. 预分词正则：BPE 之前的粗切分"); show(SEP)
show("cl100k_base:")
show(f"  {enc._pat_str}")
show("o200k_base:")
show(f"  {enc2._pat_str}")
show()
pat = re.compile(enc._pat_str)
pat2 = re.compile(enc2._pat_str)
show("预分词块 (正则粗切)  vs  最终 token:")
for s in ["Hello world, 你好 world!", "don't  it's  3.14159"]:
    show(f"  文本: {s!r}")
    show(f"    cl100k 粗切: {pat.findall(s)}")
    show(f"    o200k  粗切: {pat2.findall(s)}")
    show(f"    cl100k 最终: {[enc.decode([i]) for i in enc.encode(s)]}")
    show(f"    o200k  最终: {[enc2.decode([i]) for i in enc2.encode(s)]}")

# ---------------------------------------------------------------- 6
show(); show(SEP); show("6. o200k_base vs cl100k_base"); show(SEP)
for name, s in samples:
    a, b_ = len(enc.encode(s)), len(enc2.encode(s))
    show(f"  {name:9s} cl100k={a:4d}  o200k={b_:4d}  节省={100 - 100*b_/a:5.1f}%")

# ---------------------------------------------------------------- 7
show(); show(SEP); show("7. 词表结构：单字节底座 vs 合并产物"); show(SEP)
ranks = enc._mergeable_ranks   # {bytes: rank}
multi = [(b, len(b)) for b in ranks if len(b) > 1]
show(f"  可合并词表大小: {len(ranks)}")
show(f"  其中多字节 token: {len(multi)}  ({100*len(multi)/len(ranks):.1f}%)  <- BPE 合并的产物")
show(f"  单字节 token:      {len(ranks)-len(multi)}  <- 兜底底座，保证任何字节可编码")
show()
show("  样例合并词 (原始字节 -> 解码文本):")
shown = 0
for b, n in multi:
    if n >= 4 and any(c.isalpha() for c in visible(b)):
        show(f"     {b.hex(' ')[:34]:<36} -> 可见形态={visible(b)!r}")
        shown += 1
        if shown >= 8:
            break

# ---------------------------------------------------------------- 8
show(); show(SEP); show("8. 特殊 token 与往返一致性"); show(SEP)
show(f"  special_tokens: {sorted(enc._special_tokens)}")
show(f"  特殊 token 会绕过 BPE，直接成为原子 id，模型可以据此切换行为模式。")
show(f"  n_vocab: {enc.n_vocab}")
s = "混合 mixed 文本 \U0001F680 with 换行\n和标点，标点。"
assert enc.decode(enc.encode(s)) == s
show("  round-trip decode(encode(x)) == x : OK")

# ---------------------------------------------------------------- 9
show(); show(SEP); show("9. 从零实现 BPE：合并算法本身"); show(SEP)

def bpe_train(word_freq, num_merges):
    merges, history = [], []
    freq = {tuple(w): f for w, f in word_freq.items()}
    for step in range(num_merges):
        pairs = {}
        for w, f in freq.items():
            for i in range(len(w) - 1):
                pairs[(w[i], w[i + 1])] = pairs.get((w[i], w[i + 1]), 0) + f
        if not pairs:
            break
        best = max(pairs, key=pairs.get)
        merges.append(best)
        top = sorted(pairs.items(), key=lambda x: -x[1])[:4]
        history.append((step, best, pairs[best], top))
        nf = {}
        for w, f in freq.items():
            nw, i = [], 0
            while i < len(w):
                if i < len(w) - 1 and (w[i], w[i + 1]) == best:
                    nw.append(w[i] + w[i + 1]); i += 2
                else:
                    nw.append(w[i]); i += 1
            nf[tuple(nw)] = nf.get(tuple(nw), 0) + f
        freq = nf
    return merges, history

def bpe_encode_word(word, merges: dict):
    w = list(word)
    while len(w) > 1:
        best_i, best_rank = None, None
        for i in range(len(w) - 1):
            r = merges.get((w[i], w[i + 1]))
            if r is not None and (best_rank is None or r < best_rank):
                best_i, best_rank = i, r
        if best_i is None:
            break
        w[best_i:best_i + 2] = [w[best_i] + w[best_i + 1]]
    return w

wf = {"low": 5, "lower": 2, "newest": 6, "widest": 3}
merges, hist = bpe_train(wf, 6)
show("  语料: " + str(wf))
for step, pair, cnt, top in hist:
    topstr = "   ".join(f"{a}+{b}:{c}" for (a, b), c in top)
    show(f"  step{step}: 最高频对 {pair[0]!r}+{pair[1]!r} x{cnt:<3} | 候选: {topstr}")
show()
show("  学到的合并规则: " + " , ".join(f"{a}+{b}" for a, b in merges))
show()
merge_map = {pair: i for i, pair in enumerate(merges)}
for w in ["lower", "newest", "widest"]:
    show(f"  编码 {w!r:9s} -> {bpe_encode_word(w, merge_map)}")
show()
show("  注意: 'lower' 里没有 'es' 这个相邻对，所以它不会被合并成 'lower' 之外的形态。")
show("  编码时不是'重新训练',而是按学到的合并优先级贪心应用。")

# ---------------------------------------------------------------- 10
show(); show(SEP); show("10. 提示词三种写法的 token 成本"); show(SEP)
variants = [
 ("啰嗦版", "为了确保最终能够给用户提供高质量的回答，请在完成所有操作之后认真检查一遍结果。"),
 ("紧凑版", "完成操作后检查结果。"),
 ("结构版", "步骤:\n1. 执行操作\n2. 检查结果\n3. 汇报"),
 ("中英版", "1. exec\n2. verify\n3. report"),
]
for name, s in variants:
    ids = enc.encode(s)
    show(f"  {name:7s} tokens={len(ids):3d} chars={len(s):3d}  {s!r}")

# ---------------------------------------------------------------- 11
show(); show(SEP); show("11. 正则规则的直接后果: 数字三位一组 / 空白独立计费"); show(SEP)
num = "1234567890"
show(f"  数字串 {num!r} 的最终 token:")
show(f"    {[enc.decode([i]) for i in enc.encode(num)]}")
show("    -> 正则里的 \\p{N}{1,3} 决定数字按 1~3 位一组切，")
show("       这是模型在长数字/算术上表现差的结构性原因。")
show()
for pad in (1, 2, 4, 8):
    s2 = " " * pad + "x = 1"
    ids = enc.encode(s2)
    show(f"  缩进 {pad} 空格 + 'x = 1' -> {len(ids)} token  "
         f"{[visible(enc.decode_single_token_bytes(i)) for i in ids]}")
show("  -> 缩进空白是独立成本；用 tab 或减少嵌套能直接省 token。")
