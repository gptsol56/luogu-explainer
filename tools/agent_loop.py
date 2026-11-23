# -*- coding: utf-8 -*-
"""
agent_loop.py -- 给模型装上手: function calling / tool use 的可复用内核

设计目标:
  - 协议无关: 同一份 ToolSpec 翻译成 Anthropic / OpenAI 两种形态
  - 校验前置: 模型填的参数一律过 schema 才执行
  - 错误可修复: 校验/执行错误翻译成模型看得懂、能照着改的说明
  - 有护栏: 步数上限、预算上限、无进展检测、trace
"""
import json
import sys

from tool_contract import validate, build_error_message


class BudgetExceeded(RuntimeError):
    pass


# ---------------------------------------------------------------- ToolSpec
class ToolSpec:
    """一个工具的声明。schema 用 JSON Schema。"""
    def __init__(self, name, description, schema):
        self.name = name
        self.description = description
        self.schema = schema or {"type": "object", "properties": {}}

    @staticmethod
    def from_mcp(tool):
        """从 MCP tools/list 的一项构造。"""
        return ToolSpec(tool["name"], tool.get("description", ""), tool.get("inputSchema") or tool.get("input_schema"))

    def to_anthropic(self):
        return {"name": self.name, "description": self.description, "input_schema": self.schema}

    def to_openai(self):
        return {"type": "function",
                "function": {"name": self.name, "description": self.description,
                             "parameters": self.schema}}


# ---------------------------------------------------------------- 错误翻译
# validate / build_error_message 已收敛到 tool_contract.py (契约层单一真值来源)。
# 本模块继续导出这两个名字, 既有调用方不用改。


# ---------------------------------------------------------------- 执行器
class Executor:
    """工具执行。两种来源: 本地函数 dict, 或 MCP 客户端。"""

    def __init__(self, fns=None, mcp=None):
        self.fns = fns or {}
        self.mcp = mcp

    def call(self, name, args):
        if name in self.fns:
            try:
                r = self.fns[name](**(args or {}))
                if isinstance(r, dict) and "content" in r:
                    return r
                txt = r if isinstance(r, str) else json.dumps(r, ensure_ascii=False, default=str)
                return {"content": [{"type": "text", "text": txt}], "isError": False}
            except Exception as ex:
                return {"content": [{"type": "text",
                                    "text": "工具执行异常: " + type(ex).__name__ + ": " + str(ex)}],
                        "isError": True}
        if self.mcp is not None:
            return self.mcp.call(name, args)
        return {"content": [{"type": "text", "text": "未知工具 " + str(name)}], "isError": True}


# ---------------------------------------------------------------- LLM 客户端
class AnthropicClient:
    def __init__(self, base, key, model, extra_headers=None):
        self.base = base.rstrip("/")
        self.key = key
        self.model = model
        self.headers = {"x-api-key": key, "anthropic-version": "2023-06-01",
                        "content-type": "application/json"}
        if extra_headers: self.headers.update(extra_headers)

    def complete(self, messages, tools=None, system=None, max_tokens=2000, tool_choice=None):
        import httpx
        body = {"model": self.model, "max_tokens": max_tokens, "messages": messages}
        if tools: body["tools"] = tools
        if system: body["system"] = system
        if tool_choice: body["tool_choice"] = tool_choice
        r = httpx.post(self.base + "/messages", json=body, headers=self.headers, timeout=180)
        if r.status_code != 200:
            raise RuntimeError("LLM HTTP " + str(r.status_code) + ": " + r.text[:400])
        j = r.json()
        calls = []
        text = ""
        for b in j.get("content", []):
            if b.get("type") == "tool_use":
                calls.append({"id": b.get("id"), "name": b.get("name"), "args": b.get("input") or {}})
            elif b.get("type") == "text":
                text += b.get("text", "")
        return {"text": text.strip(), "tool_calls": calls, "usage": j.get("usage", {}), "raw": j}


class OpenAIClient:
    def __init__(self, base, key, model):
        self.base = base.rstrip("/")
        self.key = key
        self.model = model
        self.headers = {"Authorization": "Bearer " + key, "content-type": "application/json"}

    def complete(self, messages, tools=None, system=None, max_tokens=2000, tool_choice=None):
        import httpx
        ms = ([{"role": "system", "content": system}] if system else []) + list(messages)
        body = {"model": self.model, "max_tokens": max_tokens, "messages": ms}
        if tools: body["tools"] = tools
        if tool_choice: body["tool_choice"] = tool_choice
        r = httpx.post(self.base + "/chat/completions", json=body, headers=self.headers, timeout=180)
        if r.status_code != 200:
            raise RuntimeError("LLM HTTP " + str(r.status_code) + ": " + r.text[:400])
        j = r.json()
        msg = (j.get("choices") or [{}])[0].get("message") or {}
        calls = []
        for tc in msg.get("tool_calls") or []:
            f = tc.get("function") or {}
            try:
                a = json.loads(f.get("arguments") or "{}")
            except Exception:
                a = {}
            calls.append({"id": tc.get("id"), "name": f.get("name"), "args": a})
        u = j.get("usage") or {}
        usage = {"input_tokens": u.get("prompt_tokens", 0), "output_tokens": u.get("completion_tokens", 0)}
        return {"text": (msg.get("content") or "").strip(), "tool_calls": calls, "usage": usage, "raw": j}


# ---------------------------------------------------------------- Agent Loop
def call_key(name, args):
    """(工具, 参数) 的稳定指纹。sort_keys 保证参数顺序不同算出同一个 key。"""
    return name + "|" + json.dumps(args or {}, ensure_ascii=False, sort_keys=True)


def run_tool_loop(llm, tools, messages, executor, system=None, max_steps=8,
                  max_tokens=2000, meter=None, protocol="anthropic",
                  validate_first=True, trace=None, no_progress_limit=2):
    """
    完整工具循环: 决策 -> 校验 -> 执行 -> 观察 -> 再决策

    返回 {"text": 最终答案, "steps": n, "trace": [...]}
    """
    wire = ([t.to_anthropic() for t in tools] if protocol == "anthropic"
            else [t.to_openai() for t in tools])
    schema_map = {t.name: t.schema for t in tools}
    msgs = list(messages)
    trace = trace if trace is not None else []
    prev_keys = set()
    repeat_streak = 0

    for step in range(1, max_steps + 1):
        r = llm.complete(msgs, tools=wire, system=system, max_tokens=max_tokens)
        if meter: meter.record(r.get("usage", {}), tag="step%d" % step)
        tc = r.get("tool_calls") or []
        tr = {"step": step, "usage": r.get("usage", {}), "text": r.get("text", "")[:200],
              "calls": [{"name": c["name"], "args": c["args"]} for c in tc]}
        trace.append(tr)
        if not tc:
            return {"text": r.get("text", ""), "steps": step, "trace": trace}

        # --- 执行每个 tool_call ---
        results = []
        for c in tc:
            name, args, cid = c["name"], (c.get("args") or {}), c.get("id")
            errs = validate(schema_map.get(name, {}), args) if validate_first else []
            if errs:
                out = {"content": [{"type": "text", "text": build_error_message(schema_map[name], errs)}],
                       "isError": True}
                tr.setdefault("rejected", []).append(name)
            else:
                out = executor.call(name, args)
                tr.setdefault("executed", []).append(name)
            results.append((cid, name, out))

        # --- 回灌 ---
        if protocol == "anthropic":
            msgs = msgs + [{"role": "assistant", "content": r["raw"]["content"]}]
            msgs = msgs + [{"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": cid,
                 "is_error": bool(out.get("isError")),
                 "content": " ".join(c.get("text", "") for c in out.get("content", []))[:6000]}
                for (cid, _n, out) in results]}]
        else:
            msgs = msgs + [{"role": "assistant", "content": r.get("text", ""),
                            "tool_calls": [{"id": c.get("id"), "type": "function",
                                           "function": {"name": c["name"],
                                                         "arguments": json.dumps(c.get("args") or {}, ensure_ascii=False)}}
                                          for c in tc]}]
            msgs = msgs + [{"role": "tool", "tool_call_id": cid,
                            "content": " ".join(c.get("text", "") for c in out.get("content", []))[:6000]}
                           for (cid, _n, out) in results]

        # --- 护栏 ---
        if meter:
            meter.guard()
        # 无进展检测: 逐 (工具, 参数) 粒度, 只统计【相邻两步】的重复。
        # 旧实现按整轮拼指纹 —— 一个 turn 里多调一个别的工具, 整轮指纹就变了,
        # 结果"同一个工具连发同一个错参数"反而检测不到 (2026-11-21 实测漏报)。
        cur_keys = set(call_key(c["name"], c.get("args") or {}) for c in tc)
        streak = repeat_streak + 1 if (cur_keys & prev_keys) else 0
        repeat_streak = streak
        prev_keys = cur_keys
        if streak >= no_progress_limit:
            stuck = sorted(cur_keys & prev_keys)
            trace.append({"step": step, "aborted": "no_progress", "calls": stuck})
            return {"text": "检测到重复调用同一工具且参数相同, 已中止(无进展)。",
                    "steps": step, "trace": trace}

    return {"text": "达到步数上限 " + str(max_steps) + ", 未完成。", "steps": max_steps, "trace": trace}


# ---------------------------------------------------------------- 确定性自测
class _ScriptedLLM:
    """按脚本返回 tool_use 的假 LLM。只用于护栏的单元测试, 不是演示。"""

    def __init__(self, script):
        self.script = list(script)
        self.i = 0

    def complete(self, messages, tools=None, system=None, max_tokens=2000, tool_choice=None):
        calls = self.script[min(self.i, len(self.script) - 1)] if self.script else []
        self.i += 1
        blocks = [{"type": "tool_use", "id": "call_%d_%d" % (self.i, k),
                   "name": n, "input": a} for k, (n, a) in enumerate(calls)]
        return {"text": "", "usage": {},
                "tool_calls": [{"id": b["id"], "name": b["name"], "args": b["input"]} for b in blocks],
                "raw": {"content": blocks}}


def _selftest():
    ok = 0
    fail = []

    def check(name, cond, detail=""):
        nonlocal ok
        if cond:
            ok += 1
        else:
            fail.append(name + ((" :: " + detail) if detail else ""))

    schema = {"type": "object", "properties": {"q": {"type": "string"}},
              "required": ["q"], "additionalProperties": False}
    tools = [ToolSpec("t" + str(i), "desc", schema) for i in range(1, 5)]
    ex = Executor(fns={"t" + str(i): (lambda **k: "ok") for i in range(1, 5)})

    def run(script):
        return run_tool_loop(_ScriptedLLM(script), tools,
                             [{"role": "user", "content": "x"}], executor=ex)

    # 1) 同一 (工具, 参数) 连续 3 轮 -> 第 3 轮中止
    r = run([[("t1", {"q": "a"})], [("t1", {"q": "a"})], [("t1", {"q": "a"})], []])
    check("同参数连发被中止", any(tr.get("aborted") == "no_progress" for tr in r["trace"]),
          json.dumps(r["trace"], ensure_ascii=False))
    check("中止发生在第 3 轮", r["steps"] == 3, "steps=%s" % r["steps"])

    # 2) 参数每轮都不同 -> 不该中止
    r = run([[("t1", {"q": "a"})], [("t1", {"q": "b"})], [("t1", {"q": "c"})], []])
    check("不同参数不中止", not any(tr.get("aborted") for tr in r["trace"]),
          json.dumps(r["trace"], ensure_ascii=False))

    # 3) 混合轮次: 只有一个调用在重复 (旧实现整轮指纹会漏报)
    r = run([[("t1", {"q": "a"}), ("t2", {"q": "z"})],
             [("t1", {"q": "a"}), ("t3", {"q": "y"})],
             [("t1", {"q": "a"}), ("t4", {"q": "x"})], []])
    check("混合轮次里的重复被中止", any(tr.get("aborted") == "no_progress" for tr in r["trace"]),
          json.dumps(r["trace"], ensure_ascii=False))

    # 4) 参数键顺序不同 -> 仍算同一个调用
    r = run([[("t1", {"q": "a", "n": 1})], [("t1", {"n": 1, "q": "a"})], [("t1", {"q": "a", "n": 1})], []])
    check("参数键顺序不同算同一调用", any(tr.get("aborted") == "no_progress" for tr in r["trace"]),
          json.dumps(r["trace"], ensure_ascii=False))

    # 5) 步数上限始终兜底
    r = run([[("t1", {"q": "a"})]] * 20 + [[]])
    check("步数上限兜底", r["steps"] <= 8, "steps=%s" % r["steps"])

    return ok, fail


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _ok, _fail = _selftest()
        print("SELFTEST: %d passed, %d failed" % (_ok, len(_fail)))
        for f in _fail:
            print("  FAIL: " + f)
        sys.exit(1 if _fail else 0)
    else:
        print(__doc__)