# -*- coding: utf-8 -*-
"""
tool_contract.py —— 可复用的「工具契约层」(schema 的单一真值来源)

把原先散落三处、互相抄写的逻辑收敛成唯一实现:
  1. validate()            —— schema -> 错误列表          (确定性约束层)
  2. build_error_message() —— 错误列表 -> 可执行修复指引   (给模型看的错误素材)
  3. harden()              —— schema 加固 (strict), 幂等
  4. common_defs()         —— 可复用的 $defs 子 schema 片段
  5. search_params()/crud_params() —— 常见参数形状
  6. tool_spec()/describe()/contract_cost() —— 组装与度量

为什么要单独成文件(实测理由):
  agent_loop.py / minimal_mcp_server.py / demo_agent_loop.py 各自抄了一份校验逻辑,
  三处必然漂移。契约层只能有一个真值来源, 否则 "模型看到的 schema" 和
  "校验器执行的 schema" 会悄悄变成两份不同的东西。

用法:
  from tool_contract import validate, build_error_message, harden, common_defs
  errs = validate(schema, args)
  if errs:
      return {"content": [{"type": "text", "text": build_error_message(schema, errs)}], "isError": True}

自测(每类故障一个可执行断言):
  python tool_contract.py --selftest
"""
import copy
import json
import sys

try:
    import jsonschema
except Exception:
    jsonschema = None

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


class ContractUnavailable(RuntimeError):
    """没装 jsonschema 时必须显式失败 —— 静默放行等于零约束。"""


# ---------------------------------------------------------------- 约束层
def validate(schema, args):
    """按 schema 校验参数, 返回错误列表 (空列表 = 合法)。

    与旧实现的关键差别: 缺 jsonschema 时【显式抛错】, 而不是静默返回 []。
    静默返回 [] = 不挂校验器 = 零约束 = 任何非法参数都能打到真实工具。
    """
    if jsonschema is None:
        raise ContractUnavailable("未安装 jsonschema, 无法执行约束层校验 (pip install jsonschema)")
    if not isinstance(schema, dict) or not schema:
        return []
    V = jsonschema.validators.validator_for(schema)
    V.check_schema(schema)
    return sorted(V(schema).iter_errors(args), key=lambda e: list(e.absolute_path))


def build_error_message(schema, errs):
    """把校验错误翻成给模型看的可执行修复指引。

    四要素: 哪个字段 / 期望什么 / 实际什么 / 这个字段是干什么的
    结尾必须有一句 "不要自行发明新字段" —— 否则模型会开始猜字段名。
    """
    props = (schema or {}).get("properties") or {}
    lines = ["参数校验失败, 工具未被执行。", ""]
    for e in errs:
        path = list(e.absolute_path)
        sub = props.get(path[0]) if path else None
        v = e.validator
        if v == "required":
            missing = e.message.split("'")[1] if "'" in e.message else str(path)
            msub = props.get(missing) or {}
            lines.append("- 缺少必填字段 " + repr(missing) + "  -> 需要 必填, 类型 " + str(msub.get("type", "string")))
            sub = msub
        elif v == "type":
            lines.append("- 字段 " + repr(path[0] if path else "(根)") + " 类型错误: 期望 " +
                         str(e.validator_value) + ", 实际 " + type(e.instance).__name__)
        elif v == "enum":
            lines.append("- 字段 " + repr(path[0] if path else "(根)") + " 取值非法: 期望只能是 " +
                         str(e.validator_value) + ", 实际 " + repr(e.instance))
        elif v == "additionalProperties":
            lines.append("- 传了 schema 没声明的字段: " + e.message)
        else:
            lines.append("- 字段 " + repr(path[0] if path else "(根)") + ": " + e.message)
        if sub and sub.get("description"):
            lines.append("    含义: " + sub["description"])
    lines.append("")
    lines.append("请按 schema 修正上述字段后重新调用, 不要自行发明新字段。")
    return "\n".join(lines)


# ---------------------------------------------------------------- 加固层
def harden(schema, enums=None):
    """加固 schema: 禁未声明字段 (additionalProperties:false) + 可选 enum 收窄。

    幂等: harden(harden(s)) == harden(s)
    代价: schema 变长 -> 常驻 prompt 的 token 变多 (用 contract_cost 量)。
    """
    s = copy.deepcopy(schema or {})
    s.setdefault("type", "object")
    s["additionalProperties"] = False
    for field, allowed in (enums or {}).items():
        prop = (s.get("properties") or {}).get(field)
        if isinstance(prop, dict):
            prop["enum"] = list(allowed)
    return s


def probe(schema, args):
    """True = 拒绝, False = 放行。用于加固前后对比。"""
    return bool(validate(schema, args))


# ---------------------------------------------------------------- 可复用 schema 片段
def common_defs():
    """可复用的 $defs 子 schema。跨工具引用同一份定义, 避免重复膨胀。"""
    return {
        "Id":        {"type": "string", "minLength": 1, "maxLength": 64, "description": "资源唯一 ID"},
        "Timestamp": {"type": "string", "format": "date-time", "description": "ISO-8601 时间戳"},
        "Email":     {"type": "string", "format": "email", "description": "邮箱地址"},
        "Keyword":   {"type": "string", "maxLength": 200, "description": "搜索关键词"},
        "Limit":     {"type": "integer", "minimum": 1, "maximum": 200, "description": "单页条数, 1-200"},
        "Offset":    {"type": "integer", "minimum": 0, "description": "偏移量"},
    }


def with_defs(schema, defs=None):
    """把 $defs 合并进 schema (同名以 schema 自带的为准)。"""
    s = copy.deepcopy(schema or {})
    merged = dict(common_defs() if defs is None else defs)
    merged.update(s.get("$defs") or {})
    s["$defs"] = merged
    return s


def search_params(defs=None):
    """常见形状 A: 搜索 + 分页。"""
    d = common_defs() if defs is None else defs
    return {
        "$defs": d,
        "type": "object",
        "properties": {
            "keyword": {"$ref": "#/$defs/Keyword"},
            "limit":   {"$ref": "#/$defs/Limit"},
            "offset":  {"$ref": "#/$defs/Offset"},
        },
        "required": ["keyword"],
        "additionalProperties": False,
    }


def crud_params(defs=None):
    """常见形状 B: 新增实体 (最小可用字段集)。"""
    d = common_defs() if defs is None else defs
    return {
        "$defs": d,
        "type": "object",
        "properties": {
            "name":  {"type": "string", "minLength": 1, "maxLength": 120, "description": "名称"},
            "email": {"$ref": "#/$defs/Email"},
            "note":  {"type": "string", "maxLength": 2000, "description": "备注"},
        },
        "required": ["name"],
        "additionalProperties": False,
    }


# ---------------------------------------------------------------- 组装与度量
def tool_spec(name, description, input_schema):
    """构造标准 MCP 工具定义 (tools/list 里的一项)。"""
    return {"name": name, "description": description, "inputSchema": input_schema}


def describe(schema):
    """一行摘要: 必填 / 可选 / 是否 strict。"""
    s = schema or {}
    props = s.get("properties") or {}
    req = list(s.get("required") or [])
    opt = [k for k in props if k not in req]
    return "必填[%s] 可选[%s] strict=%s" % (",".join(req) or "-", ",".join(opt) or "-",
                                            s.get("additionalProperties") is False)


def contract_cost(schema, enc=None):
    """schema 的 token 成本 —— 常驻 prompt, 每轮都付。装不了 tiktoken 返回 None。"""
    try:
        if enc is None:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(json.dumps(schema, ensure_ascii=False)))
    except Exception:
        return None


# ---------------------------------------------------------------- 自测
def _selftest():
    ok = 0
    fail = []

    def check(name, cond, detail=""):
        nonlocal ok
        if cond:
            ok += 1
        else:
            fail.append(name + ((" :: " + detail) if detail else ""))

    base = {
        "type": "object",
        "properties": {
            "content_type": {"type": "string", "description": "Optional engine content type, e.g. json or toon."},
            "input": {"type": "string", "description": "The payload to compress."},
        },
        "required": ["input"],
    }

    # 1) 合法参数
    check("合法参数通过", validate(base, {"input": "x"}) == [])

    # 2) 缺必填 -> 错误消息必须含 字段名 + 语义 + 禁止发明字段
    errs = validate(base, {"content_type": "json"})
    check("缺必填被拦", len(errs) == 1, "errors=%d" % len(errs))
    msg = build_error_message(base, errs)
    check("错误含字段名", "'input'" in msg, msg)
    check("错误含语义", "含义: The payload to compress." in msg, msg)
    check("错误含禁止发明字段", "不要自行发明新字段" in msg, msg)

    # 3) 类型错
    msg = build_error_message(base, validate(base, {"input": 12345}))
    check("类型错信息含期望/实际", "类型错误: 期望 string, 实际 int" in msg, msg)

    # 4) enum 越界 (加固后)
    tight = harden(base, {"content_type": ["json", "toon"]})
    errs = validate(tight, {"input": "x", "content_type": "xml"})
    check("enum 越界被拦", len(errs) >= 1)
    check("enum 错误信息正确", "取值非法" in build_error_message(tight, errs))

    # 5) 未声明字段
    check("加固后多传字段被拦", probe(tight, {"input": "x", "bogus": 1}) is True)
    check("原 schema 放行多传字段", probe(base, {"input": "x", "bogus": 1}) is False)

    # 6) harden 幂等 + 不改原对象
    check("harden 幂等", harden(tight) == tight)
    check("harden 不改原对象", base.get("additionalProperties") is None)

    # 7) $defs / $ref 复用
    sp = search_params()
    check("$ref 合法参数通过", validate(sp, {"keyword": "abc", "limit": 10}) == [])
    check("$ref 缺必填被拦", probe(sp, {}) is True)
    check("$ref 多传字段被拦", probe(sp, {"keyword": "a", "zzz": 1}) is True)
    check("$ref 越界被拦", probe(sp, {"keyword": "a", "limit": 9999}) is True)
    check("$defs 片段齐全", set(common_defs()) == {"Id", "Timestamp", "Email", "Keyword", "Limit", "Offset"})
    check("with_defs 合并不丢原有", set(with_defs({"$defs": {"X": {"type": "string"}}})["$defs"]) >= {"Id", "X"})

    # 8) 缺 jsonschema 必须显式失败, 不能静默放行
    global jsonschema
    saved = jsonschema
    try:
        jsonschema = None
        raised = False
        try:
            validate(base, {"bogus": 1})
        except ContractUnavailable:
            raised = True
        check("缺 jsonschema 显式失败(不静默放行)", raised)
    finally:
        jsonschema = saved

    # 9) 组装 / 度量
    ts = tool_spec("demo_tool", "demo desc", base)
    check("tool_spec 结构正确", ts["name"] == "demo_tool" and "inputSchema" in ts)
    check("describe 正确", "必填[input]" in describe(base))
    check("contract_cost 返回 int", isinstance(contract_cost(base), int))

    # 10) 错误消息在多错误时全部列出
    msg = build_error_message(base, validate(base, {}))
    check("多错误全部列出", msg.count("- 缺少必填字段") == 1)

    return ok, fail


def _overview():
    print("=" * 74)
    print("工具契约层概览 (tool_contract)")
    print("=" * 74)
    print("可复用的 $defs 片段:")
    for k, v in common_defs().items():
        print("  %-10s %s" % (k, json.dumps(v, ensure_ascii=False)))
    print()
    print("常见形状 A - search_params():")
    print("  " + describe(search_params()))
    print("  " + json.dumps(search_params(), ensure_ascii=False)[:220] + " ...")
    print()
    print("常见形状 B - crud_params():")
    print("  " + describe(crud_params()))
    print()
    base = {"type": "object",
            "properties": {"input": {"type": "string", "description": "The payload to compress."}},
            "required": ["input"]}
    print("加固成本对比 (schema 常驻 prompt, 每轮都付):")
    print("  原始 schema token 数 : %s" % contract_cost(base))
    print("  加固后 schema token 数: %s" % contract_cost(harden(base)))


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _ok, _fail = _selftest()
        print("SELFTEST: %d passed, %d failed" % (_ok, len(_fail)))
        for f in _fail:
            print("  FAIL: " + f)
        sys.exit(1 if _fail else 0)
    else:
        _overview()
