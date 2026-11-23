# -*- coding: utf-8 -*-
"""
minimal_mcp_server.py -- 最小但完整的 MCP stdio 服务器

设计要点:
  1. schema 是真的: 启动时通过 JSON-RPC 从上游真实 MCP server 抓 tools/list
  2. 实现是真的: tools/call 转发给上游真实执行, 不伪造结果
  3. 中间加一层校验 + 错误归一化: 这才是本 demo 要演示的东西

协议: JSON-RPC 2.0 over stdio, 换行分隔。
注意: 日志一律走 stderr, 写 stdout 会破坏 JSON-RPC 帧。
"""
import sys, json, os, subprocess, threading

from tool_contract import validate, build_error_message

# --- 编码加固 ---
# Windows 中文 locale 默认 cp936(GBK)。JSON-RPC 管道上两端编码不一致就会
# UnicodeDecodeError, 而且读线程一旦死掉, 请求会静默变成 timeout。
# 1) 管道 JSON 一律 ensure_ascii=True -> 线上只走纯 ASCII, 与任何 locale 无关
# 2) 子进程强制 UTF-8 + errors=replace -> 永不因解码失败抛异常
# 3) 读线程异常要显式上报, 不能变成超时
for _s in (sys.stdin, sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

UPSTREAM = os.environ.get("MCP_UPSTREAM", r"C:\Users\CHATGPT\.caveman\bin\caveman-mcp.exe")
EXPOSED_TOOL = os.environ.get("MCP_TOOL", "caveman_compress")

def log(*a):
    print(*a, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- 上游客户端
class Upstream:
    def __init__(self, cmd):
        _env = dict(os.environ)
        _env["PYTHONUTF8"] = "1"
        _env["PYTHONIOENCODING"] = "utf-8"
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                                  errors="replace", bufsize=1, env=_env)
        self._id = 0
        self.lock = threading.Lock()
        self.request("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                    "clientInfo": {"name": "minimal-mcp-server", "version": "1.0"}})
        self.notify("notifications/initialized")
        self.schemas = {}
        for t in self.request("tools/list", {})["tools"]:
            self.schemas[t["name"]] = t

    def notify(self, method, params=None):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self.p.stdin.write(json.dumps(msg, ensure_ascii=True) + "\n")
        self.p.stdin.flush()

    def request(self, method, params=None, timeout=30):
        with self.lock:
            self._id += 1
            rid = self._id
            msg = {"jsonrpc": "2.0", "id": rid, "method": method}
            msg["params"] = params if params is not None else {}
            self.p.stdin.write(json.dumps(msg, ensure_ascii=True) + "\n")
            self.p.stdin.flush()
            box = {}

            def rd():
                try:
                    while True:
                        line = self.p.stdout.readline()
                        if not line:
                            box["eof"] = True
                            return
                        try:
                            obj = json.loads(line)
                        except Exception:
                            continue
                        if obj.get("id") == rid:
                            box["obj"] = obj
                            return
                except Exception as ex:
                    box["exc"] = type(ex).__name__ + ": " + str(ex)
            t = threading.Thread(target=rd, daemon=True)
            t.start()
            t.join(timeout)
            if "exc" in box:
                raise RuntimeError("读取上游输出失败: " + str(box["exc"]))
            if "obj" not in box:
                raise TimeoutError("upstream " + method + " timeout")
            return box["obj"].get("result", {})

    def call(self, name, args, timeout=60):
        return self.request("tools/call", {"name": name, "arguments": args}, timeout)


# ---------------------------------------------------------------- 校验层
# validate / build_error_message 已收敛到 tool_contract.py (契约层单一真值来源)。
# 这里继续导出这两个名字, 保持既有调用方不用改。


# ---------------------------------------------------------------- MCP server
def main():
    if not os.path.exists(UPSTREAM):
        print("[fatal] 找不到上游 MCP server: " + UPSTREAM, file=sys.stderr)
        print("        请用环境变量 MCP_UPSTREAM 指向正确的可执行文件路径。", file=sys.stderr)
        sys.exit(2)
    up = Upstream([UPSTREAM])
    real_tool = up.schemas[EXPOSED_TOOL]
    schema = real_tool["inputSchema"]
    log("[server] 上游 schema 已抓取: " + EXPOSED_TOOL + " required=" + str(schema.get("required")) +
        " props=" + str(list((schema.get("properties") or {}).keys())))

    out = sys.stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        method = req.get("method")
        rid = req.get("id")
        params = req.get("params") or {}

        if rid is None:
            continue  # notification, 不回包

        def reply(result=None, error=None):
            msg = {"jsonrpc": "2.0", "id": rid}
            if error is not None:
                msg["error"] = error
            else:
                msg["result"] = result if result is not None else {}
            out.write(json.dumps(msg, ensure_ascii=True) + "\n")
            out.flush()

        try:
            if method == "initialize":
                reply({"protocolVersion": "2024-11-05",
                       "capabilities": {"tools": {"listChanged": False}},
                       "serverInfo": {"name": "minimal-mcp-server", "version": "1.0"}})
            elif method == "ping":
                reply({})
            elif method == "tools/list":
                reply({"tools": [real_tool]})
            elif method == "resources/list":
                reply({"resources": []})
            elif method == "prompts/list":
                reply({"prompts": []})
            elif method == "tools/call":
                name = params.get("name")
                args = params.get("arguments") or {}
                if name != EXPOSED_TOOL:
                    reply({"content": [{"type": "text", "text": "未知工具 " + str(name)}],
                           "isError": True})
                    continue
                errs = validate(schema, args)
                if errs:
                    log("[server] 校验拦截, " + str(len(errs)) + " 条错误")
                    reply({"content": [{"type": "text",
                                        "text": build_error_message(schema, errs)}],
                           "isError": True})
                    continue
                try:
                    r = up.call(name, args)
                except Exception as ex:
                    reply({"content": [{"type": "text", "text": "上游执行失败: " +
                                        type(ex).__name__ + ": " + str(ex)}],
                           "isError": True})
                    continue
                if r.get("isError"):
                    txt = " ".join(c.get("text", "") for c in r.get("content", []))
                    reply({"content": [{"type": "text", "text": "上游工具返回错误: " + txt}],
                           "isError": True})
                    continue
                reply({"content": r.get("content", []), "isError": False})
            else:
                reply(error={"code": -32601, "message": "method not found: " + str(method)})
        except Exception as ex:
            log("[server] 内部错误 " + repr(ex))
            reply(error={"code": -32603, "message": str(ex)})


if __name__ == "__main__":
    main()