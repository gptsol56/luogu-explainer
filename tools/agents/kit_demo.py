# -*- coding: utf-8 -*-
"""
kit_demo.py —— 复用证明: 换一套 schema + 换一组工具, 不改一行 loop

用真实 LLM (MiniMax-M3) + 真实执行 (本地函数作为工具来源), 证明:
  1. tool_contract 造出来的 schema, agent_loop 直接吃, 不需要改 loop
  2. 同一套 loop 能同时挂多套不同 schema 的工具, 由模型自己选
  3. 多步任务(先查后建)能一次跑完 —— 这是 loop 相对单次调用的核心价值
  4. 校验前置 + 可执行错误在换 schema 之后依然生效

跑法:
  python kit_demo.py
"""
import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import yaml

from tool_contract import (validate, build_error_message, harden, probe,
                           search_params, crud_params, tool_spec, describe, contract_cost)
from agent_loop import ToolSpec, AnthropicClient, Executor, run_tool_loop
from cost_manager import CostMeter


def hdr(t):
    print()
    print("=" * 78)
    print(t)
    print("=" * 78)


def show(t=""):
    print(t)


# ---------------------------------------------------------------- 真实工具 (本地函数)
CREATED = []


def create_customer(**kw):
    CREATED.append(kw)
    return {"id": "C-%04d" % len(CREATED), "created": kw}


def search_customer(**kw):
    kw.get("keyword")
    return {"items": [{"id": "C-0001", "name": "张三"}], "total": 1, "echo": kw}


# ---------------------------------------------------------------- LLM
def load_llm(provider="minimax-cn", model="MiniMax-M3"):
    cfg = yaml.safe_load(open(r"C:\Users\CHATGPT\.minimax\config.yaml", encoding="utf-8"))
    p = (cfg.get("custom_provider") or {})[provider]
    base = p["options"]["baseURL"].rstrip("/") + "/v1"
    return AnthropicClient(base, p["options"]["apiKey"], model)


# ---------------------------------------------------------------- 复用件: 零硬编码造工具
def build_tools():
    """两个工具, 两套完全不同的 schema, 全部由 tool_contract 组装。"""
    return [
        tool_spec("create_customer",
                  "Create a new customer record. name is required; email and note are optional.",
                  crud_params()),
        tool_spec("search_customer",
                  "Search customers by keyword. Supports pagination via limit and offset.",
                  search_params()),
    ]


def main():
    hdr("阶段 0: 用可复用 schema 片段造两个工具 (零硬编码)")
    raw = build_tools()
    for t in raw:
        show("  " + t["name"].ljust(18) + describe(t["inputSchema"]))
    show()
    show("  search_customer 的 schema 片段:")
    show("  " + json.dumps(raw[1]["inputSchema"], ensure_ascii=False)[:300] + " ...")

    hdr("阶段 1: 校验前置 —— 故意传非法参数, 看可执行错误")
    schema = raw[0]["inputSchema"]
    errs = validate(schema, {"email": "zhang@example.com"})
    show("  错误数: %d" % len(errs))
    show("  返回给模型的说明:")
    for ln in build_error_message(schema, errs).split("\n"):
        show("    | " + ln)

    hdr("阶段 2: 真实 LLM + 真实执行 —— 一套 loop 挂两套 schema, 多步任务")
    llm = load_llm()
    meter = CostMeter(model="MiniMax-M3", budget_tokens=60000)
    tools = [ToolSpec.from_mcp(t) for t in raw]
    show("  LLM: %s @ %s" % (llm.model, llm.base))
    show("  挂载工具: " + ", ".join(t.name for t in tools))
    show()

    task = ("请帮我做两件事: "
            "1) 用 search_customer 查一下客户关键字 '张'; "
            "2) 用 create_customer 新增一个客户, 姓名 张三, 邮箱 zhang@example.com, 备注 VIP。")

    res = run_tool_loop(
        llm, tools, [{"role": "user", "content": task}],
        executor=Executor(fns={"create_customer": create_customer,
                               "search_customer": search_customer}),
        system="你是一个 CRM 助手, 需要操作客户数据时请调用工具, 不要凭空编造结果。",
        max_steps=6, meter=meter, protocol="anthropic",
    )

    show("  步数: %d" % res["steps"])
    for tr in res["trace"]:
        for c in tr.get("calls", []):
            show("    step%d 调用 %s(%s)" % (tr["step"], c["name"],
                                            json.dumps(c["args"], ensure_ascii=False)[:120]))
        if tr.get("rejected"):
            show("      被校验拦截: " + ", ".join(tr["rejected"]) + "  <- 模型当场改对")
    show()
    show("  真实执行落库: " + json.dumps(CREATED, ensure_ascii=False))
    show()
    show("  模型最终答案:")
    for ln in res["text"].split("\n"):
        show("    " + ln)
    show()
    show("  账本: " + json.dumps(meter.report(), ensure_ascii=False))

    hdr("阶段 3: 同一套 loop, 换一份 schema 不用改任何代码")
    alt = tool_spec("create_customer_v2",
                    "Create a customer with a required name only (minimal schema).",
                    {"type": "object",
                     "properties": {"name": {"type": "string", "description": "客户姓名"}},
                     "required": ["name"],
                     "additionalProperties": False})
    show("  新工具: " + alt["name"] + "  " + describe(alt["inputSchema"]))
    show("  -> loop 侧零改动: 同样传给 run_tool_loop(llm, tools, ...)")

    hdr("阶段 4: 加固的代价 (schema 常驻 prompt, 每轮都付)")
    loose = {"type": "object",
             "properties": {"name": {"type": "string", "description": "客户姓名"},
                            "email": {"type": "string", "description": "邮箱"}},
             "required": ["name"]}
    tight = harden(loose)
    show("  宽松 schema token 数 : %s   %s" % (contract_cost(loose), describe(loose)))
    show("  加固 schema token 数 : %s   %s" % (contract_cost(tight), describe(tight)))
    show("  探针 多传字段: 宽松=%s 加固=%s" % ("拒绝" if probe(loose, {"name": "x", "zz": 1}) else "放行",
                                                "拒绝" if probe(tight, {"name": "x", "zz": 1}) else "放行"))
    show("  -> 加固 = 多花几个 token, 换掉一类本来会打到真实工具的脏参数。")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
