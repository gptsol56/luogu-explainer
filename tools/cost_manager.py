# -*- coding: utf-8 -*-
"""
cost_manager.py -- Agent 成本管理

两个层次:
  1) token 记账 (ground truth, 永远可算, 与模型无关)
  2) 金额换算 (projection, 依赖模型单价, 单价可变)
另加上下文构成分析: 钱到底花在哪一块 (system / tools / history / output)
"""
import json

try:
    import tiktoken
    _ENC = {}
    def _enc(name="cl100k_base"):
        if name not in _ENC:
            _ENC[name] = tiktoken.get_encoding(name)
        return _ENC[name]
except Exception:
    _ENC = {}
    def _enc(name="cl100k_base"):
        raise RuntimeError("需要 tiktoken: pip install tiktoken")


class BudgetExceeded(RuntimeError):
    pass


# 单价表: 美元 / 1M tokens。模型单价会变, 请按官方定价页更新。
# None 表示没有该模型的单价 -> 只报 token, 不报钱 (不做假账)。
PRICES = {
    # model_id: (input, output, cache_write, cache_read)
    "MiniMax-M3": (None, None, None, None),
    "MiniMax-M3.1-Flash": (None, None, None, None),
    "gpt-4o": (2.50, 10.00, 3.125, 1.25),
    "claude-sonnet": (3.00, 15.00, 3.75, 0.30),
}


class CostMeter:
    """逐次记账 + 预算熔断。线程不安全但够用(单 agent 串行调用)。"""

    def __init__(self, model="MiniMax-M3", budget_usd=None, budget_tokens=None, prices=None):
        self.model = model
        self.budget_usd = budget_usd
        self.budget_tokens = budget_tokens
        self.prices = dict(PRICES)
        if prices: self.prices.update(prices)
        self.calls = []          # 每次调用的明细
        self.total = {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0}

    # ---------------- 记账 ----------------
    def record(self, usage, tag="", kind="call"):
        """usage 形如 {"input_tokens":..,"output_tokens":..,
                  "cache_creation_input_tokens":..,"cache_read_input_tokens":..}"""
        u = usage or {}
        rec = {
            "tag": tag,
            "kind": kind,
            "input": int(u.get("input_tokens", 0) or 0),
            "output": int(u.get("output_tokens", 0) or 0),
            "cache_write": int(u.get("cache_creation_input_tokens", 0) or 0),
            "cache_read": int(u.get("cache_read_input_tokens", 0) or 0),
        }
        rec["total_tokens"] = rec["input"] + rec["output"] + rec["cache_write"] + rec["cache_read"]
        rec["usd"] = self.price_of(rec)
        self.calls.append(rec)
        for k in self.total:
            self.total[k] += rec[k]
        return rec

    def price_of(self, rec):
        p = self.prices.get(self.model)
        if not p or p[0] is None:
            return None
        pi, po, pw, pr = p
        usd = (rec["input"] * pi + rec["output"] * po +
               rec["cache_write"] * pw + rec["cache_read"] * pr) / 1_000_000
        return round(usd, 6)

    # ---------------- 汇总 ----------------
    def snapshot(self):
        total_tok = sum(self.total.values())
        usd = None
        if self.prices.get(self.model) and self.prices[self.model][0] is not None:
            usd = round(sum(c["usd"] for c in self.calls if c["usd"] is not None), 6)
        denom = self.total["input"] + self.total["cache_read"]
        hit = (self.total["cache_read"] / denom) if denom else 0.0
        return {
            "model": self.model,
            "calls": len(self.calls),
            "tokens": dict(self.total),
            "total_tokens": total_tok,
            "cache_hit_rate": round(hit, 4),
            "usd": usd,
            "budget_usd": self.budget_usd,
        }

    # ---------------- 熔断 ----------------
    def guard(self):
        """超预算就抛。必须在每次模型调用【之后】立刻调用。"""
        s = self.snapshot()
        if self.budget_usd is not None:
            if s["usd"] is None:
                raise RuntimeError(
                    "设了 budget_usd 但模型 " + self.model + " 没有单价, 金额熔断无法生效。"
                    "请先在 PRICES 里配该模型单价, 或改用 budget_tokens。")
            if s["usd"] > self.budget_usd:
                raise BudgetExceeded("预算超限: 已花 ${:.4f} > 上限 ${:.4f}".format(s["usd"], self.budget_usd))
        if self.budget_tokens is not None and s["total_tokens"] > self.budget_tokens:
            raise BudgetExceeded("token 预算超限: 已用 {} > 上限 {}".format(s["total_tokens"], self.budget_tokens))
        return s

    def report(self):
        s = self.snapshot()
        lines = ["成本汇总:"]
        lines.append("  模型      : " + s["model"])
        lines.append("  调用次数  : " + str(s["calls"]))
        lines.append("  input     : " + str(s["tokens"]["input"]))
        lines.append("  output    : " + str(s["tokens"]["output"]))
        lines.append("  cache写   : " + str(s["tokens"]["cache_write"]))
        lines.append("  cache读   : " + str(s["tokens"]["cache_read"]))
        lines.append("  总 token  : " + str(s["total_tokens"]))
        lines.append("  缓存命中  : {:.1%}".format(s["cache_hit_rate"]))
        lines.append("  金额      : " + ("${:.4f}".format(s["usd"]) if s["usd"] is not None else "(该模型无单价, 只报 token)"))
        lines.append("  逐次明细:")
        for i, c in enumerate(self.calls, 1):
            lines.append("    {}. {:<22} in={:<6} out={:<6} cw={:<6} cr={:<6} {}".format(
                i, c["tag"] or "-", c["input"], c["output"], c["cache_write"], c["cache_read"],
                ("${:.6f}".format(c["usd"]) if c["usd"] is not None else "")))
        return "\n".join(lines)


def analyze_context(system=None, tools=None, messages=None, output_text=None,
                    encoding="cl100k_base"):
    """上下文构成分析: 钱花在哪个块上。这是唯一 actionable 的成本视角。"""
    e = _enc(encoding)
    parts = {}
    if system: parts["system"] = len(e.encode(system))
    if tools:
        parts["tools"] = len(e.encode(json.dumps(tools, ensure_ascii=False)))
    if messages:
        parts["history"] = len(e.encode(json.dumps(messages, ensure_ascii=False)))
    if output_text: parts["output"] = len(e.encode(output_text))
    total = sum(parts.values())
    pct = {k: (v / total if total else 0) for k, v in parts.items()}
    return {"parts": parts, "total": total, "pct": pct}


def advise(an, meter=None):
    """基于构成分析给可执行建议。"""
    out = []
    p = an["parts"]; pct = an["pct"]
    if pct.get("tools", 0) > 0.30:
        out.append("[高] 工具 schema 占 {:.0%} —— 精简 description, 或按场景只加载用得到的工具".format(pct["tools"]))
    if pct.get("history", 0) > 0.50:
        out.append("[高] 历史占 {:.0%} —— 主动裁剪/摘要, 或把大内容外置成文件让工具按需读".format(pct["history"]))
    if pct.get("output", 0) > 0.40:
        out.append("[中] 输出占 {:.0%} —— 输出是最贵的一段, 限制 max_tokens / 要求简洁".format(pct["output"]))
    if an["total"] > 60000:
        out.append("[中] 单轮上下文 {} token, 偏大 —— 注意 lost in the middle".format(an["total"]))
    if not out:
        out.append("[ok] 构成健康, 无明显浪费点")
    if meter:
        s = meter.snapshot()
        if s["cache_hit_rate"] < 0.3 and s["calls"] > 1:
            out.append("[中] 缓存命中率仅 {:.0%} —— 系统提示与工具定义要逐字节稳定".format(s["cache_hit_rate"]))
    return out