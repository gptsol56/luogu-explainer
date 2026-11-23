# -*- coding: utf-8 -*-
import sys, json, subprocess, threading
sys.stdout.reconfigure(encoding='utf-8')
import jsonschema, tiktoken

SEP = "=" * 78
def show(t=""): print(t)
def show2(a, b): print(f"  {a} {b}")

EXE = r"C:\Users\CHATGPT\.caveman\bin\caveman-mcp.exe"
p = subprocess.Popen([EXE], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                     stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1)
def send(o):
    p.stdin.write(json.dumps(o, ensure_ascii=False) + "\n"); p.stdin.flush()
def read_msg(t=12):
    box = {}
    def w(): box['line'] = p.stdout.readline()
    th = threading.Thread(target=w, daemon=True); th.start(); th.join(t)
    if not box.get('line'): return None
    try: return json.loads(box['line'])
    except Exception: return None

send({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05",
      "capabilities":{},"clientInfo":{"name":"schema-probe","version":"1.0"}}})
init = read_msg()
send({"jsonrpc":"2.0","method":"notifications/initialized"})
send({"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}})
tools = (read_msg() or {}).get("result", {}).get("tools", [])
try: p.stdin.close(); p.terminate()
except Exception: pass

show(SEP); show("1. 真实 MCP 工具 schema（本机 caveman server, tools/list）"); show(SEP)
t0 = tools[0]
show(json.dumps(t0, ensure_ascii=False, indent=2))

show(); show(SEP); show("2. schema 的两层: 描述层 vs 约束层"); show(SEP)
show("  [描述层]  name / description / properties.*.description")
show("             -> 只有模型会读。它决定【要不要调这个工具、参数填什么】")
show("  [约束层]  type / required / enum / minimum / additionalProperties")
show("             -> 只有校验器会读。它决定【这份数据合不合法】")
show()
sch = t0["inputSchema"]
V = jsonschema.validators.validator_for(sch); V.check_schema(sch); v = V(sch)
cases = [
    ("完全合法",            {"input": "hello"}),
    ("缺 required 字段",     {"content_type": "json"}),
    ("类型不对",             {"input": 123}),
    ("多传未声明字段",       {"input": "x", "bogus": 1, "__proto__": "y"}),
    ("枚举越界(本schema无enum)", {"input": "x", "content_type": "任何字符串"}),
]
for label, payload in cases:
    errs = list(v.iter_errors(payload))
    show2(f"{label:26s}", ("通过" if not errs else "拒绝 -> " + errs[0].message))
show()
show("  >>> 注意最后两行都【通过】: 这个 schema 没有 additionalProperties:false,")
show("      content_type 也没有 enum。所以 schema 写了什么, 约束就是什么。")
show("  >>> schema 本身不执行任何东西; 不挂校验器 = 零约束。")
show()

show(SEP); show("3. JSON Schema 关键词速查（AI 场景常用）"); show(SEP)
KEYS = [
 ("type",            '"string" | "number" | "integer" | "boolean" | "array" | "object" | "null"'),
 ("properties",      "对象各字段的子 schema"),
 ("required",        '必填字段名数组, 如 ["input"]'),
 ("enum",            "枚举白名单, 模型只能从中选"),
 ("items",           "数组元素 schema"),
 ("minimum/maximum", "数值上下界"),
 ("minLength/maxLength", "字符串长度界"),
 ("pattern",         "正则约束"),
 ("default",         "默认值 (仅提示, 不保证模型填)"),
 ("additionalProperties", "false = 禁止未声明字段 (strict 模式必开)"),
 ("$defs + $ref",    "复用子 schema, 避免大 schema 重复膨胀"),
 ("oneOf/anyOf",     "多分支"),
 ("format",          "date-time / email / uri (多数引擎不强制)"),
]
for k, v in KEYS:
    show2(f"  {k:<24s}", v)
show()

show(SEP); show("4. schema 的 token 成本（schema 是常驻上下文的！）"); show(SEP)
enc = tiktoken.get_encoding("cl100k_base")
MIN = {"type":"object","properties":{"q":{"type":"string"}},"required":["q"]}
RICH = {
  "type":"object",
  "properties":{
    "query":{"type":"string","description":"Full-text search query. Supports quoted phrases, boolean operators AND/OR/NOT, and field filters like path:src/*.ts. Max 512 characters."},
    "scope":{"type":"string","enum":["all","repo","cwd","open_files"],"description":"Where to search. 'all' searches the entire indexed workspace including git history; 'repo' searches tracked files only."},
    "max_results":{"type":"integer","minimum":1,"maximum":200,"description":"Maximum number of hits to return. Default 50. Higher values increase latency."},
    "include_content":{"type":"boolean","description":"Whether to include matched file contents in the response. Disabling this cuts token usage significantly."},
    "filters":{"type":"array","items":{"type":"object","properties":{
        "ext":{"type":"string","description":"File extension filter, e.g. .ts"},
        "modified_after":{"type":"string","format":"date-time"},
        "author":{"type":"string"}},"required":["ext"],"additionalProperties":False}}
  },
  "required":["query"],
  "additionalProperties":False
}
for name, s in [("最小 schema", MIN), ("详细 schema", RICH)]:
    txt = json.dumps(s, ensure_ascii=False)
    ids = enc.encode(txt)
    show2(f"  {name:<12s}", f"token={len(ids):4d}  chars={len(txt):4d}")
d = len(enc.encode(json.dumps(RICH, ensure_ascii=False))) - len(enc.encode(json.dumps(MIN, ensure_ascii=False)))
show()
show(f"  详细描述比最小描述多花 {d} token / 每个工具。")
show("  >>> 30 个工具各多 150 token = 4500 token【每轮都在付】。")
show("      -> 描述要写【够用】, 不是【写满】。")
show()

show(SEP); show("5. 模型侧: schema 怎么真正起作用"); show(SEP)
show("  A. Function Calling —— 模型输出【调用意图 + 参数】")
show("     模型只生成 JSON, 真正的约束来自解码时的 grammar:")
show("       schema --编译--> 语法/FSM --> 逐 token 只允许合法路径")
show("     这叫 constrained decoding, 是【真强制】, 不是【提示】。")
show("  B. Structured Output —— 约束模型最终回答")
show("     OpenAI: response_format=json_schema (+ strict)   Anthropic: output_format / tool 强制")
show("  C. tool_choice —— 强制模型必须调用(或必须不调用)某个工具")
show("  D. MCP 侧: inputSchema 只作描述 + 你自己校验")
show("     MCP 规范不要求 server 侧强制校验; 真执行前请自己过一遍 validator。")
