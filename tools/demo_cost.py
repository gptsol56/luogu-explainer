# -*- coding: utf-8 -*-
"""
demo_cost.py -- 成本管理 + function calling 内核 端到端实测

  A. 上下文构成分析: 钱到底花在哪一块
  B. 三种 schema 策略的 token 成本对比
  C. 真实 LLM 调用 + 逐次记账 + 缓存命中率
  D. 预算熔断
  E. agent_loop.run_tool_loop 端到端 (MCP 执行器)
"""
import os, sys, json, copy
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from demo_agent_loop import McpClient, Llm, LONG_TEXT
from agent_loop import ToolSpec, Executor, run_tool_loop, AnthropicClient
from cost_manager import CostMeter, analyze_context, advise, BudgetExceeded

SEP = "=" * 78
def show(t=""): print(t)
def hdr(t):
    show(); show(SEP); show(t); show(SEP)


def main():
    cli = McpClient(os.path.join(HERE, "minimal_mcp_server.py"))
    tools_raw = cli.request("tools/list")["tools"]
    specs = [ToolSpec.from_mcp(t) for t in tools_raw]
    show("  工具: " + ", ".join(t.name for t in specs))

    # ---------- A ----------
    hdr("A. 上下文构成分析 (钱花在哪一块)")
    sysmsg = "你是压缩助手。用户会给一段较长的文本, 请调用 compress 工具把它压缩。只调用一次工具。"
    msgs = [{"role": "user", "content": "请压缩这段文本:\n\n" + LONG_TEXT}]
    wire = [t.to_anthropic() for t in specs]
    an = analyze_context(system=sysmsg, tools=wire, messages=msgs,
                         output_text="(预期输出: 压缩结果摘要, 约 200 token)")
    show("  " + "块".ljust(10) + "token".rjust(8) + "占比".rjust(9))
    for k, v in an["parts"].items():
        show("  " + k.ljust(12) + str(v).rjust(8) + ("{:.1%}".format(an["pct"][k])).rjust(9))
    show("  " + "合计".ljust(12) + str(an["total"]).rjust(8))
    show()
    for line in advise(an):
        show("  " + line)
    show()

    # ---------- B ----------
    hdr("B. 三种 schema 策略的 token 成本 (工具常驻成本)")
    lean = ToolSpec(specs[0].name, "压缩长文本。",
                    {"type": "object",
                     "properties": {"input": {"type": "string", "description": "要压缩的内容."}},
                     "required": ["input"]})
    extra = ToolSpec("search_docs", "搜索文档. 输入关键词, 返回命中的片段.",
                     {"type": "object",
                      "properties": {"query": {"type": "string", "description": "关键词."},
                                    "limit": {"type": "integer", "description": "条数上限."}},
                      "required": ["query"]})
    strategies = [
        ("现状: 真实 schema 逐字", [specs[0].to_anthropic()]),
        ("精简: 短描述 + 最小 schema", [lean.to_anthropic()]),
        ("精简 + 多装 1 个工具", [lean.to_anthropic(), extra.to_anthropic()]),
        ("全量 + 多装 1 个工具(合成)", [specs[0].to_anthropic(), extra.to_anthropic()]),
    ]
    show("  " + "策略".ljust(28) + "tools token".rjust(12) + "相对现状".rjust(12))
    base_tok = None
    for label, tl in strategies:
        t = analyze_context(tools=tl)["total"]
        if base_tok is None: base_tok = t
        show("  " + label.ljust(30) + str(t).rjust(10) +
             ("{:.0%}".format(t / base_tok - 1).rjust(12) if base_tok else ""))
    show()
    show("  >>> 工具 schema 是【每轮都付】的常驻成本。真实项目里 20~40 个工具,")
    show("      一次精简可能省下每轮数千 token, 且模型选错工具的概率同步下降。")

    # ---------- C ----------
    hdr("C. 真实 LLM 调用 + 逐次记账")
    meter = CostMeter(model="MiniMax-M3")   # 该模型无公开单价 -> 只报 token
    llm = Llm(model=os.environ.get("DEMO_MODEL", "MiniMax-M3"))
    anth = AnthropicClient(llm.base, llm.key, llm.model)
    ex = Executor(mcp=cli)
    r1 = anth.complete(msgs, tools=wire, system=sysmsg)
    meter.record(r1["usage"], tag="手写一次调用")
    show("  模型返回 tool_calls: " + str([c["name"] for c in r1["tool_calls"]]))
    show("  usage: " + json.dumps(r1["usage"], ensure_ascii=False))
    show()
    res = run_tool_loop(llm=anth, tools=specs, messages=msgs, executor=ex,
                       system=sysmsg, max_steps=4, meter=meter)
    show("  run_tool_loop 结果: steps=" + str(res["steps"]))
    show("  最终答案(前 160 字): " + res["text"][:160])
    show("  trace:")
    for t in res["trace"]:
        show("    " + json.dumps(t, ensure_ascii=False)[:200])
    show()
    show(meter.report())
    show()

    # ---------- D ----------
    hdr("D. 预算熔断")
    tight = CostMeter(model="MiniMax-M3", budget_tokens=100)
    tight.record(r1["usage"], tag="故意超额")
    try:
        tight.guard()
        show("  未触发熔断 (意外)")
    except BudgetExceeded as e:
        show("  [token 预算] 已触发: " + str(e))
    show()
    noprice = CostMeter(model="MiniMax-M3", budget_usd=0.01)
    noprice.record(r1["usage"], tag="无单价")
    try:
        noprice.guard()
        show("  [金额预算] 未触发 (意外)")
    except BudgetExceeded as e:
        show("  [金额预算] 已触发: " + str(e))
    except RuntimeError as e:
        show("  [金额预算] 明确报错(而不是静默失效): " + str(e))
    show("  >>> 护栏分两种: budget_tokens 永远可用(纯 token); budget_usd 需要该模型有单价。")
    show("      没有单价却设了金额预算 -> 立即报错, 不允许静默放行。")

    # ---------- E ----------
    hdr("E. 错误 -> 校验 -> 自修复 (走 agent_loop 内核)")
    bad_specs = [specs[0]]
    msgs_bad = [{"role": "user", "content": "请压缩这段文本:\n\n" + LONG_TEXT}]
    # 先人为构造一次非法参数, 走内核的校验分支
    from agent_loop import validate, build_error_message
    errs = validate(specs[0].schema, {"content_type": "json"})
    show("  校验非法参数 -> 错误说明:")
    for line in build_error_message(specs[0].schema, errs).splitlines():
        show("    | " + line)
    show()
    show("  run_tool_loop 的护栏: max_steps / meter.guard() / 无进展检测(逐调用粒度: 同一(工具,参数)连续出现 2 次即中止)")

    cli.close()


if __name__ == "__main__":
    main()