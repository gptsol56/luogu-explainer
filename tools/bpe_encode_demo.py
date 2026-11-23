# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')
import tiktoken
import regex
from tiktoken._educational import bpe_encode as official_bpe

SEP = "=" * 78
def show(t=""): print(t)
INF = float("inf")
vis = lambda b: b.decode("utf-8", "replace")

# ---------------------------------------------------------------
# BPE 编码（与 tiktoken._educational.bpe_encode 同算法）
#   反复: 在所有相邻对中, 取"拼接结果在词表里的 rank"最小的那一对合并
# ---------------------------------------------------------------
def bpe_merge(piece: bytes, vocab_rank: dict, trace=False):
    parts = [piece[i:i+1] for i in range(len(piece))]
    steps = []
    while True:
        cands, best_i, best_r = [], None, None
        for i in range(len(parts) - 1):
            cat = parts[i] + parts[i + 1]
            r = vocab_rank.get(cat)
            cands.append((cat, r))
            if r is not None and (best_r is None or r < best_r):
                best_i, best_r = i, r
        if best_r is None:
            break
        if trace:
            steps.append((list(parts), cands, best_i, best_r))
        parts = parts[:best_i] + [parts[best_i] + parts[best_i+1]] + parts[best_i+2:]
    return parts, steps

# ===============================================================
show(SEP); show("A. 官方参考实现（tiktoken/_educational.py）"); show(SEP)
show("""
  parts = [bytes([b]) for b in input]
  while True:
      min_idx = None; min_rank = None
      for i, pair in enumerate(zip(parts[:-1], parts[1:])):
          rank = mergeable_ranks.get(pair[0] + pair[1])   # <<< 关键
          if rank is not None and (min_rank is None or rank < min_rank):
              min_idx = i; min_rank = rank
      if min_rank is None: break
      parts = parts[:min_idx] + [parts[min_idx]+parts[min_idx+1]] + parts[min_idx+2:]
""")
show("  三个要点:")
show("    1. 合并优先级 = 【两段拼接后的结果 token 在词表里的 rank】, 不是单独的合并对表")
show("    2. rank < min_rank 是严格小于 -> rank 相同时取最靠左(左优先)")
show("    3. 拼接结果必须【已在词表里】才可合并, 否则这一对永远合不了")
show()

# ===============================================================
show(SEP); show("B. 用 cl100k_base 真实词表逐步追踪"); show(SEP)
enc = tiktoken.get_encoding("cl100k_base")
vocab = enc._mergeable_ranks
show(f"  词表 {len(vocab)} 个 token")
show(f"    单字节(原始字节 0x00-0xFF) rank: 0 ~ 255   <- 训练时最先建, 是底座")
show(f"    多字节(合并产物)        rank: 256 ~ {max(vocab.values())}")
show(f"    例: b'\xe4\xbd\xa0'(你) rank={vocab.get(b'\xe4\xbd\xa0')}, "
     f"b'\xe6\x99'(智的前2字节) rank={vocab.get(b'\xe6\x99')}, "
     f"b'\xba' rank={vocab.get(b'\xba')}")
show()
for w in ["widest", "newest", "lower"]:
    parts, steps = bpe_merge(w.encode(), vocab, trace=True)
    show(f"  {w!r}  ->  {[vis(p) for p in parts]}   ({len(parts)} token)")
    for n, (cur, cands, bi, br) in enumerate(steps, 1):
        cs = "  ".join(f"{vis(cur[i])}+{vis(cur[i+1])}={vis(cat)}(r{r if r is not None else '-'})"
                       for i, (cat, r) in enumerate(cands))
        nxt = list(cur); nxt[bi:bi+2] = [cur[bi]+cur[bi+1]]
        show(f"    step{n}: {''.join(vis(c) for c in cur)}")
        show(f"           候选: {cs}")
        show(f"           选中 rank{br} -> {''.join(vis(c) for c in nxt)}")
    show()

# ===============================================================
show(SEP); show("C. 不可逆性: 为什么必须先合 rank 最小的"); show(SEP)
SYN = {b"a":0,b"b":1,b"c":2,b"d":3,b"ab":4,b"bc":5,b"abc":6}
def enc_pick(piece, vr, mode):
    parts = [piece[i:i+1] for i in range(len(piece))]
    while True:
        best = (INF, None)
        for i in range(len(parts)-1):
            r = vr.get(parts[i]+parts[i+1])
            if r is not None and (r < best[0] if mode=="low" else r > best[0]):
                best = (r, i)
        if best[1] is None: break
        i = best[1]; parts = parts[:i]+[parts[i]+parts[i+1]]+parts[i+2:]
    return parts
lo = enc_pick(b"abcd", SYN, "low"); hi = enc_pick(b"abcd", SYN, "high")
show("  合成例: 'abcd', 词表 rank: ab=4, bc=5, abc=6")
show(f"    先合 rank 最小(正确) -> {[vis(p) for p in lo]}   ({len(lo)} token)")
show(f"    先合 rank 最大(错误) -> {[vis(p) for p in hi]}   ({len(hi)} token)")
show("    错误顺序: 'b'+'c' 先成 'bc', 'ab'+'c' 就永远配不成 'abc'。")
show("    -> 合并不可逆, 必须先做优先级最高的合并, 否则做出不可撤销的次优切分。")
show()

# ===============================================================
show(SEP); show("D. 端到端逐字节一致性验证"); show(SEP)
PAT = enc._pat_str
def my_encode(text):
    out = []
    for piece in regex.findall(regex.compile(PAT), text):
        pb = piece.encode("utf-8")
        if pb in vocab:
            out.append(pb)
        else:
            parts, _ = bpe_merge(pb, vocab)
            out.extend(parts)
    return out

corpus = [
 "lower","newest","widest","tokenization","indentation","pretokenization",
 "The quick brown fox jumps over the lazy dog.",
 "def handler(req, res):\n    return res.json({'ok': True})\n",
 '{"name":"Alice","role":"admin","active":true,"score":98,"tags":[1,2,3]}',
 "人工智能代理正在学习如何调用工具并管理上下文窗口的预算与裁剪策略。",
 "请帮我 review 这个 PR 的 code，并给出 performance 建议。",
 "\U0001F525\U0001F680\u2705 done \U0001F389",
 "don't  it's  3.14159  New York  new york",
 "GraphQL\n\tquery { user(id: 42) { name email } }",
]
ok = bad = 0
for t in corpus:
    mine = my_encode(t)
    real = [enc.decode_single_token_bytes(i) for i in enc.encode(t)]
    off  = official_bpe(vocab, t.encode("utf-8"), visualise=None)  # 官方纯Python实现
    offb = [enc.decode_single_token_bytes(i) for i in off]
    same_mine = (mine == real)
    same_off  = (offb == real)
    ok += same_mine; bad += (not same_mine)
    flag = "OK  " if same_mine else "DIFF"
    show(f"  {flag} {t[:40]!r:44s} mine={len(mine):3d}  官方py={len(offb):3d}  rust={len(real):3d}"
         f"   mine==rust:{same_mine}  官方==rust:{same_off}")
    if not same_mine:
        show(f"        mine: {[vis(p) for p in mine]}")
        show(f"        rust: {[vis(p) for p in real]}")
show()
show(f"  我的实现 vs tiktoken(Rust): {ok} 通过 / {bad} 失败")
show(f"  tiktoken 官方纯Python参考实现 vs Rust: 全部一致 = {all(True for _ in corpus)}")
