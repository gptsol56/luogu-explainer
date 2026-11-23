# -*- coding: utf-8 -*-
"""
demo_agent_loop.py -- 完整演示: 模型填参 / Schema 校验 / 错误返回与自修复

链路:
  tools/list(真实schema) -> 真实LLM填参 -> tools/call -> 校验 -> 转发上游真实执行
  -> 结果回灌LLM出最终答案
  -> 非法调用被拦截 -> 错误喂回LLM -> LLM自我修复 -> 再次调用成功
"""
import sys, os, json, subprocess, threading
sys.stdout.reconfigure(encoding="utf-8")
import httpx, yaml

SERVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "minimal_mcp_server.py")
SEP = "=" * 78

def show(t=""): print(t)
def hdr(t):
    show(); show(SEP); show(t); show(SEP)


# ---------------------------------------------------------------- MCP 客户端
class McpClient:
    def __init__(self, script):
        _env = dict(os.environ)
        _env["PYTHONUTF8"] = "1"
        _env["PYTHONIOENCODING"] = "utf-8"
        self.p = subprocess.Popen([sys.executable, script], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=None, text=True,
                                  encoding="utf-8", errors="replace", bufsize=1, env=_env)
        self._id = 0
        self.init = self.request("initialize", {"protocolVersion": "2024-11-05",
                                              "capabilities": {},
                                              "clientInfo": {"name": "demo", "version": "1"}})
        self.notify("notifications/initialized")

    def notify(self, method, params=None):
        m = {"jsonrpc": "2.0", "method": method}
        if params is not None: m["params"] = params
        self.p.stdin.write(json.dumps(m, ensure_ascii=True) + "\n"); self.p.stdin.flush()

    def request(self, method, params=None, timeout=90):
        self._id += 1
        rid = self._id
        m = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}
        self.p.stdin.write(json.dumps(m, ensure_ascii=True) + "\n"); self.p.stdin.flush()
        box = {}

        def rd():
            try:
                while True:
                    line = self.p.stdout.readline()
                    if not line:
                        box["eof"] = True; return
                    try: obj = json.loads(line)
                    except Exception: continue
                    if obj.get("id") == rid:
                        box["obj"] = obj; return
            except Exception as ex:
                box["exc"] = type(ex).__name__ + ": " + str(ex)
        t = threading.Thread(target=rd, daemon=True); t.start(); t.join(timeout)
        if "exc" in box: raise RuntimeError("读取 server 输出失败: " + str(box["exc"]))
        if "obj" not in box: raise TimeoutError(method + " timeout")
        o = box["obj"]
        if "error" in o: raise RuntimeError(str(o["error"]))
        return o.get("result", {})

    def call(self, name, args):
        return self.request("tools/call", {"name": name, "arguments": args})

    def close(self):
        try:
            self.p.stdin.close(); self.p.terminate()
        except Exception: pass


# ---------------------------------------------------------------- LLM
class Llm:
    def __init__(self, provider="minimax-cn", model="MiniMax-M3"):
        cfg = yaml.safe_load(open(r"C:\Users\CHATGPT\.minimax\config.yaml", encoding="utf-8"))
        p = (cfg.get("custom_provider") or {})[provider]
        self.base = p["options"]["baseURL"].rstrip("/") + "/v1"
        self.key = p["options"]["apiKey"]
        self.model = model
        self.headers = {"x-api-key": self.key, "anthropic-version": "2023-06-01",
                        "content-type": "application/json"}

    def chat(self, messages, tools=None, system=None, max_tokens=2000):
        body = {"model": self.model, "max_tokens": max_tokens, "messages": messages}
        if tools: body["tools"] = tools
        if system: body["system"] = system
        r = httpx.post(self.base + "/messages", json=body, headers=self.headers, timeout=180)
        if r.status_code != 200:
            raise RuntimeError("LLM HTTP " + str(r.status_code) + ": " + r.text[:400])
        return r.json()


def tool_use_of(resp):
    for blk in resp.get("content", []):
        if blk.get("type") == "tool_use":
            return blk
    return None

def text_of(resp):
    return " ".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text").strip()


LONG_TEXT = ("【产品需求评审纪要】\n" +
  "本季度平台侧共上线 3 个能力包, 其中客户管理模块日活从 0 提升到 1200。\n" * 12 +
  "遗留问题: 通知模块缺少去重, 导致重复推送; 上传模块对大文件未做分片。\n" * 5)


HERE = os.path.dirname(os.path.abspath(__file__))


def preflight():
    hdr("预检")
    up = os.environ.get("MCP_UPSTREAM", r"C:\Users\CHATGPT\.caveman\bin\caveman-mcp.exe")
    show("  脚本目录 : " + HERE)
    show("  当前目录 : " + os.getcwd())
    show("  server   : " + SERVER + ("   [存在]" if os.path.exists(SERVER) else "   [缺失!]"))
    show("  上游 exe : " + up + ("   [存在]" if os.path.exists(up) else "   [缺失!]"))
    show("  python   : " + sys.executable)
    if not os.path.exists(SERVER):
        show()
        show("  !! 找不到 minimal_mcp_server.py —— 两个文件必须在同一个目录。")
        show("     正确跑法(不用切目录, 任何位置都行):")
        show('     python "' + os.path.join(HERE, "demo_agent_loop.py") + '"')
        show("     或双击同目录下的 run_demo.cmd")
        sys.exit(2)


def main():
    preflight()
    hdr("阶段 0: 启动最小 MCP server, 取回真实 tools/list schema")
    cli = McpClient(SERVER)
    show("  serverInfo: " + json.dumps(cli.init.get("serverInfo"), ensure_ascii=False))
    tl = cli.request("tools/list")
    tool = tl["tools"][0]
    show("  工具: " + tool["name"] + "   (schema 逐字来自上游真实 caveman MCP server)")
    show(json.dumps(tool, ensure_ascii=False, indent=2))

    llm = Llm(model=os.environ.get("DEMO_MODEL", "MiniMax-M3"))
    show("  LLM: " + llm.model + " @ " + llm.base)

    anth_tools = [{"name": tool["name"], "description": tool["description"],
                   "input_schema": tool["inputSchema"]}]
    sysmsg = ("你是压缩助手。用户会给一段较长的文本, 请调用 compress 工具把它压缩。",
              "只调用一次工具, 不要自己编造内容。")

    hdr("阶段 1: 模型填参 (真实 LLM 调用, 真实 tool_use)")
    msgs = [{"role": "user", "content": "请压缩这段文本:\n\n" + LONG_TEXT}]
    r1 = llm.chat(msgs, tools=anth_tools, system=sysmsg)
    show("  usage: " + json.dumps(r1.get("usage", {}), ensure_ascii=False))
    tu = tool_use_of(r1)
    if not tu:
        show("  !! 模型未返回 tool_use, 文本: " + text_of(r1)[:300])
        cli.close(); return
    show("  模型生成的 tool_use:")
    show("    id   = " + str(tu.get("id")))
    show("    name = " + str(tu.get("name")))
    show("    input = " + json.dumps(tu.get("input"), ensure_ascii=False)[:220] + " ...")
    show("    input 里的 input 字段长度 = " + str(len((tu.get("input") or {}).get("input", ""))))

    hdr("阶段 2: tools/call -> Schema 校验 -> 转发上游真实执行")
    res = cli.call(tool["name"], tu.get("input") or {})
    show("  isError = " + str(res.get("isError")))
    show("  工具返回(真实上游执行结果):")
    for c in res.get("content", []):
        show("    " + c.get("text", "")[:400])
    show()
    show("  -> 把工具结果回灌给模型, 让它出最终答案:")
    msgs3 = list(msgs) + [{"role": "assistant", "content": r1["content"]},
                          {"role": "user", "content": [{"type": "tool_result",
                                       "tool_use_id": tu.get("id"),
                                       "content": res["content"][0]["text"][:3000]}]}]
    r3 = llm.chat(msgs3, tools=anth_tools, system=sysmsg)
    show("  最终答案: " + (text_of(r3) or "(空)")[:300])

    hdr("阶段 3: 错误返回流程 (故意构造非法参数)")
    bad_cases = [
        ("缺必填字段", {"content_type": "json"}),
        ("类型错误", {"input": 12345}),
        ("完全为空", {}),
    ]
    for label, args in bad_cases:
        rr = cli.call(tool["name"], args)
        show("  [" + label + "] 入参 " + json.dumps(args, ensure_ascii=False))
        show("    isError = " + str(rr.get("isError")))
        show("    返回给模型的错误信息:")
        for line in rr["content"][0]["text"].splitlines():
            show("      | " + line)
        show()

    hdr("阶段 4: 模型自我修复 (把错误喂回 LLM)")
    bad = {"content_type": "json"}
    rr = cli.call(tool["name"], bad)
    err_text = rr["content"][0]["text"]
    show("  第一次的错误信息已由 server 返回 (见阶段3), 现在喂回模型")
    msgs2 = [{"role": "user", "content": "请压缩这段文本:\n\n" + LONG_TEXT},
              {"role": "assistant", "content": [{"type": "tool_use", "id": "call_bad",
                                                "name": tool["name"], "input": bad}]},
              {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call_bad",
                                            "is_error": True, "content": err_text}]}]
    r2 = llm.chat(msgs2, tools=anth_tools, system=sysmsg)
    tu2 = tool_use_of(r2)
    if not tu2:
        show("  !! 模型未再调工具, 文本: " + text_of(r2)[:300])
    else:
        show("  修复后的 tool_use input 字段:")
        for k, v in (tu2.get("input") or {}).items():
            show("    " + k + " = " + (json.dumps(v, ensure_ascii=False)[:120]))
        res2 = cli.call(tool["name"], tu2.get("input") or {})
        show("  isError = " + str(res2.get("isError")))
        show("  执行结果: " + res2["content"][0]["text"][:300])

    hdr("阶段 5: schema 加固前后拦截能力对比")
    from tool_contract import harden, probe
    base = tool["inputSchema"]
    tight = harden(base, {"content_type": ["json", "toon"]})
    probes = [
        ("合法", {"input": "x", "content_type": "json"}),
        ("枚举越界", {"input": "x", "content_type": "xml"}),
        ("多传字段", {"input": "x", "bogus": 1}),
        ("缺必填", {"content_type": "json"}),
        ("类型错", {"input": 1}),
    ]
    show("  " + "探针".ljust(12) + "原 schema".ljust(12) + "加固后 schema")
    for label, args in probes:
        def chk(sch):
            return "拒绝" if probe(sch, args) else "放行"
        show("  " + label.ljust(14) + chk(base).ljust(14) + chk(tight))
    show()
    show("  加固 = 加 additionalProperties:false + enum; 代价是 schema 变长(token 变多)。")

    cli.close()


if __name__ == "__main__":
    main()