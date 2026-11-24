# -*- coding: utf-8 -*-
"""
luogu_explainer.py - 洛谷题目自动讲解核心库

用途:
  1. 抓取洛谷题目 (题号 -> 题面纯文本), 也支持直接粘贴题面;
  2. 调用大模型生成面向自学/教学的讲解 Markdown。接口形状有两种: Anthropic 风格
     (POST {base}/v1/messages) 与 OpenAI 风格 (POST {base}/chat/completions),
     可选厂商见 explainer/providers.json;
  3. 自带 --selftest, 完全离线 (不联网、不读注册表密钥、不需要洛谷账号)。

设计原则 (与仓库根的 luogu_punch.py 保持一致):
  - 密钥只从环境变量读, Windows 上回退到注册表 HKCU\\Environment; 绝不落盘、绝不进日志;
  - 任何错误信息都不含密钥本身 (统一走 _redact);
  - 接口语义以服务端实际返回为准, 不靠猜 (例如 code=201 必须结合 message 判定);
  - 自检离线可跑, 适合放进 CI。

用法:
    python explainer/luogu_explainer.py --pid P1001
    python explainer/luogu_explainer.py --file 题面.txt --out 讲解.md
    python explainer/luogu_explainer.py --selftest

凭据 (环境变量, 每个厂商一套, 见 explainer/providers.json):
    MINIMAX_API_KEY      MiniMax 平台密钥
    MINIMAX_BASE_URL     可选, 默认 https://api.minimaxi.com/anthropic
    MINIMAX_MODEL        可选, 默认 MiniMax-M3.1-Flash
    DEEPSEEK_API_KEY     DeepSeek (另有 DEEPSEEK_BASE_URL / DEEPSEEK_MODEL)
    MOONSHOT_API_KEY     Kimi (另有 MOONSHOT_BASE_URL / MOONSHOT_MODEL)
    DASHSCOPE_API_KEY    百炼 (另有 DASHSCOPE_BASE_URL / DASHSCOPE_MODEL)
    ZHIPUAI_API_KEY      智谱 (另有 ZHIPUAI_BASE_URL / ZHIPUAI_MODEL)
    LLM_API_KEY          自定义端点 (另有 LLM_BASE_URL / LLM_MODEL)
    LUOGU_CLIENT_ID      抓题用, 对应洛谷 Cookie 的 __client_id
    LUOGU_UID            抓题用, 对应洛谷 Cookie 的 _uid
"""

from __future__ import annotations

import argparse
import contextlib
import html as html_mod
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Optional
from urllib.parse import unquote_plus

LUOGU_BASE = "https://www.luogu.com.cn"
PROBLEM_PAGE = LUOGU_BASE + "/problem/{pid}?_contentOnly=1"
PROBLEM_DETAIL_API = LUOGU_BASE + "/fe/api/problem/detail/{pid}"

API_KEY_ENV = "MINIMAX_API_KEY"
BASE_URL_ENV = "MINIMAX_BASE_URL"
MODEL_ENV = "MINIMAX_MODEL"
CLIENT_ID_ENV = "LUOGU_CLIENT_ID"
UID_ENV = "LUOGU_UID"

DEFAULT_BASE_URL = "https://api.minimaxi.com/anthropic"
DEFAULT_MODEL = "MiniMax-M3.1-Flash"
DEFAULT_MAX_TOKENS = 4096
ANTHROPIC_VERSION = "2023-06-01"

# 模型厂商预设表: 唯一真源是 explainer/providers.json。后端与浏览器端读的是同一份
# 文件, 所以"页面上能选哪些模型"和"服务端认识哪些模型"不会各说各话。
PROVIDERS_PATH = Path(__file__).resolve().parent / "providers.json"
PROTOCOL_ANTHROPIC = "anthropic"
PROTOCOL_OPENAI = "openai"

# Markdown 代码块围栏, 用转义写法避免源码里出现反引号
FENCE = "\u0060" * 3

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

LOGIN_REQUIRED_HINT = ("洛谷题目接口需要登录态，请在环境变量设置 "
                       "LUOGU_CLIENT_ID / LUOGU_UID 后重试，或直接粘贴题面。")

DIFFICULTY_NAMES = {
    0: "暂无评定", 1: "入门", 2: "普及-", 3: "普及", 4: "提高+",
    5: "提高", 6: "省选-", 7: "省选", 8: "NOI-", 9: "NOI", 10: "NOI+/CTSC",
}

# 提示词模板: 唯一真源。浏览器端 (GitHub Pages 静态站) 读的是同一份 JSON,
# 所以本机代理模式与静态 BYOK 模式生成的提示词完全一致, 不会出现两端漂移。
TEMPLATE_PATH = Path(__file__).resolve().parent / "prompt_template.json"


class ExplainerError(RuntimeError):
    """讲解过程中的可预期错误。"""


def load_prompt_template() -> dict[str, Any]:
    """读取提示词模板 JSON。缺失或字段不对时直接报错, 不做静默兜底。"""
    try:
        with open(TEMPLATE_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as exc:
        raise ExplainerError(
            "提示词模板读取失败: " + str(TEMPLATE_PATH) + " (" + type(exc).__name__ + ")"
        ) from exc
    except ValueError as exc:
        raise ExplainerError("提示词模板不是合法 JSON: " + str(TEMPLATE_PATH)) from exc
    if not isinstance(data, dict):
        raise ExplainerError("提示词模板必须是 JSON 对象")
    for key in ("required_sections", "styles", "user_prompt_template"):
        if key not in data:
            raise ExplainerError("提示词模板缺少字段: " + key)
    return data


# 讲解固定小节 (模板与自检共用同一份定义, 避免两处漂移)
REQUIRED_SECTIONS = tuple(load_prompt_template()["required_sections"])


def load_providers() -> dict[str, Any]:
    """读取模型厂商预设表。缺失或字段不对时直接报错, 不做静默兜底。"""
    try:
        with open(PROVIDERS_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as exc:
        raise ExplainerError(
            "模型预设表读取失败: " + str(PROVIDERS_PATH) + " (" + type(exc).__name__ + ")"
        ) from exc
    except ValueError as exc:
        raise ExplainerError("模型预设表不是合法 JSON: " + str(PROVIDERS_PATH)) from exc
    if not isinstance(data, dict):
        raise ExplainerError("模型预设表必须是 JSON 对象")
    protocols = data.get("protocols")
    providers = data.get("providers")
    if not isinstance(protocols, dict) or not protocols:
        raise ExplainerError("模型预设表缺少 protocols")
    if not isinstance(providers, list) or not providers:
        raise ExplainerError("模型预设表缺少 providers")
    ids: list[str] = []
    for spec in providers:
        if not isinstance(spec, dict):
            raise ExplainerError("模型预设表里有一条不是对象")
        for field in ("id", "label", "protocol"):
            if not spec.get(field):
                raise ExplainerError("模型预设缺少字段: " + field)
        if str(spec["protocol"]) not in protocols:
            raise ExplainerError("模型预设引用了未知协议: " + str(spec["protocol"]))
        ids.append(str(spec["id"]))
    default = str(data.get("default_provider") or "")
    if default and default not in ids:
        raise ExplainerError("默认厂商不在 providers 列表里: " + default)
    return data


def find_provider(provider_id: Optional[str] = None) -> dict[str, Any]:
    """按 id 取厂商预设。找不到就报错, 并把当前可选的 id 列出来。"""
    table = load_providers()
    wanted = (provider_id or table.get("default_provider") or "").strip()
    for spec in table["providers"]:
        if str(spec.get("id")) == wanted:
            return spec
    ids = ", ".join(str(s.get("id")) for s in table["providers"])
    raise ExplainerError("未知模型厂商: " + (wanted or "(空)") + "。当前可选: " + ids)


# --------------------------------------------------------------------------
# 纯文本处理
# --------------------------------------------------------------------------

_SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_BLOCK_TAGS = ("br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
                "pre", "section", "table", "ul", "ol", "blockquote", "hr")
_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(s: str) -> str:
    """把题面 HTML 清洗成纯文本: 去标签、保留换行、解实体、压掉多余空白。"""
    if not s:
        return ""
    text = str(s)
    text = _SCRIPT_RE.sub(" ", text)
    # 块级标签换成换行, 保留语义结构
    for tag in _BLOCK_TAGS:
        text = re.sub(r"</?%s[^>]*>" % tag, "\n", text, flags=re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = _TAG_RE.sub("", text)
    text = html_mod.unescape(text)
    text = text.replace("\u00a0", " ").replace("\u3000", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for line in text.split("\n"):
        line = re.sub(r"[ \t\f\v]+", " ", line).strip()
        lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def classify_target(target: str) -> str:
    """判断输入是题号 ("P1001" / "1001") 还是粘贴的题面文本。"""
    text = (target or "").strip()
    if not text:
        return "text"
    if re.fullmatch(r"[A-Za-z]{1,3}\d{2,6}", text):
        return "pid"
    if re.fullmatch(r"\d{3,6}", text):
        return "pid"
    return "text"


def normalize_pid(pid: str) -> str:
    """把 "1001" / "p1001" 归一成 "P1001"。"""
    text = (pid or "").strip()
    if not text:
        return ""
    if text.isdigit():
        return "P" + text
    m = re.fullmatch(r"([A-Za-z]{1,3})(\d{2,6})", text)
    if m:
        return m.group(1).upper() + m.group(2)
    return text.upper()


def title_from_text(text: str) -> str:
    """从粘贴的题面里猜一个标题 (第一行非空内容)。"""
    for line in (text or "").splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line[:60]
    return "粘贴的题面"


# --------------------------------------------------------------------------
# 提示词
# --------------------------------------------------------------------------

def build_prompt(problem_text: str, style: str = "面向初学者") -> str:
    """生成面向自学/教学的讲解提示词, 要求模型输出固定小节的 Markdown。

    模板正文来自 explainer/prompt_template.json (唯一真源), 这里只做占位符替换;
    浏览器端的静态站读的是同一个文件, 两端提示词不会漂移。
    """
    template = load_prompt_template()
    body = (problem_text or "").strip()
    tone = (style or "面向初学者").strip()
    sections = "\n".join("## " + name for name in template["required_sections"])
    prompt = (
        str(template["user_prompt_template"])
        .replace("{{style}}", tone)
        .replace("{{sections}}", sections)
        .replace("{{problem}}", body)
    )
    if "{{" in prompt:
        raise ExplainerError("提示词模板存在未替换的占位符")
    return prompt



# --------------------------------------------------------------------------
# 配置 (环境变量 -> Windows 注册表回退)
# --------------------------------------------------------------------------

def _read_registry_env() -> dict[str, str]:
    """读取 HKCU\\Environment 里的用户环境变量。非 Windows 或读取失败时返回空字典。"""
    if os.name != "nt":
        return {}
    try:
        import winreg  # noqa: PLC0415
    except Exception:
        return {}
    values: dict[str, str] = {}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            # QueryInfoKey 返回 (子键数, 值的个数, 最后修改时间), 这里要的是值的个数
            count = winreg.QueryInfoKey(key)[1]
            for index in range(count):
                name, value, _ = winreg.EnumValue(key, index)
                if name:
                    values[str(name)] = str(value)
    except OSError:
        return {}
    return values


def resolve_config(provider: Optional[str] = None,
                   use_registry: bool = True) -> dict[str, str]:
    """解析某个厂商的调用配置: 先环境变量, 再 (可选) Windows 注册表回退。

    走哪套环境变量由 providers.json 决定 (key_env / base_url_env / model_env),
    所以加一个新厂商只要在那份 JSON 里加一条, 这个函数不用动。
    """
    spec = find_provider(provider)
    key_env = str(spec.get("key_env") or API_KEY_ENV)
    base_env = str(spec.get("base_url_env") or BASE_URL_ENV)
    model_env = str(spec.get("model_env") or MODEL_ENV)
    base_url = (os.environ.get(base_env) or "").strip()
    api_key = (os.environ.get(key_env) or "").strip()
    model = (os.environ.get(model_env) or "").strip()
    if use_registry:
        registry = _read_registry_env()
        base_url = base_url or registry.get(base_env, "").strip()
        api_key = api_key or registry.get(key_env, "").strip()
        model = model or registry.get(model_env, "").strip()
    if not api_key:
        raise ExplainerError(
            "缺少 " + str(spec.get("label") or key_env) + " 的 API Key：未找到环境变量 "
            + key_env + "。\n"
            "请先设置 (PowerShell): setx " + key_env + " \"<你的密钥>\"\n"
            "注意 setx 只对之后新开的进程生效, 当前终端请先执行 "
            "$env:" + key_env + " = \"<你的密钥>\""
        )
    return {
        "base_url": (base_url or str(spec.get("base_url") or DEFAULT_BASE_URL)).rstrip("/"),
        "api_key": api_key,
        "model": model or str(spec.get("model") or DEFAULT_MODEL),
        "protocol": str(spec.get("protocol") or PROTOCOL_ANTHROPIC),
        "provider": str(spec.get("id") or ""),
        "key_env": key_env,
    }


def config_snapshot(provider: Optional[str] = None,
                    use_registry: bool = True) -> dict[str, Any]:
    """给 /api/health 用的非抛出快照: 只暴露"有没有", 绝不把密钥放进响应体。"""
    try:
        spec = find_provider(provider)
    except ExplainerError:
        spec = {}
    key_env = str(spec.get("key_env") or API_KEY_ENV)
    base_env = str(spec.get("base_url_env") or BASE_URL_ENV)
    model_env = str(spec.get("model_env") or MODEL_ENV)
    base_url = (os.environ.get(base_env) or "").strip()
    api_key = (os.environ.get(key_env) or "").strip()
    model = (os.environ.get(model_env) or "").strip()
    if use_registry:
        registry = _read_registry_env()
        base_url = base_url or registry.get(base_env, "").strip()
        api_key = api_key or registry.get(key_env, "").strip()
        model = model or registry.get(model_env, "").strip()
    return {
        "base_url": (base_url or str(spec.get("base_url") or DEFAULT_BASE_URL)).rstrip("/"),
        "api_key": api_key,
        "model": model or str(spec.get("model") or DEFAULT_MODEL),
        "has_key": bool(api_key),
        "protocol": str(spec.get("protocol") or PROTOCOL_ANTHROPIC),
        "provider": str(spec.get("id") or ""),
        "key_env": key_env,
    }


def load_luogu_cookie() -> str:
    """从环境变量拼洛谷 Cookie; 凭据缺失时返回空串。"""
    client_id = (os.environ.get(CLIENT_ID_ENV) or "").strip()
    uid = (os.environ.get(UID_ENV) or "").strip()
    if client_id and uid:
        return "__client_id=" + client_id + "; _uid=" + uid + ";"
    return ""


# --------------------------------------------------------------------------
# MiniMax 调用 (Anthropic 兼容端点)
# --------------------------------------------------------------------------

def _all_key_envs() -> list[str]:
    """列出所有可能被用到的密钥环境变量名。读不到预设表时退回 MiniMax 那套。"""
    names = [API_KEY_ENV]
    try:
        for spec in load_providers().get("providers") or []:
            if isinstance(spec, dict) and spec.get("key_env"):
                names.append(str(spec["key_env"]))
    except ExplainerError:
        pass
    return names


def _redact(text: str, secret: str = "") -> str:
    """把可能出现的密钥从文本里抹掉, 保证异常信息里不泄漏。

    抹的不只是当前这一个 —— 任何厂商的密钥环境变量都扫一遍, 因为报错信息里
    可能带出别处的调试片段。
    """
    out = str(text)
    secrets: list[str] = []
    if secret:
        secrets.append(secret)
    for name in _all_key_envs():
        value = (os.environ.get(name) or "").strip()
        if value:
            secrets.append(value)
    for item in secrets:
        out = out.replace(item, "***REDACTED***")
    return out


def _default_transport(url: str, headers: dict[str, str], body: dict[str, Any],
                       timeout: float) -> tuple[int, str]:
    """真实 HTTP POST。requests 延迟导入, 让 --selftest 在没装依赖时也能跑。"""
    try:
        import requests  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - 环境问题
        raise ExplainerError("缺少依赖 requests, 请先 pip install requests") from exc
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=timeout)
    except requests.exceptions.Timeout as exc:
        raise ExplainerError("调用模型超时 (" + str(timeout) + "s)") from exc
    except requests.exceptions.RequestException as exc:
        raise ExplainerError("调用模型失败: " + type(exc).__name__ + ": " + str(exc)) from exc
    return resp.status_code, resp.text or ""


def _endpoint(base_url: str, suffix: str) -> str:
    """拼接口地址。base_url 已经写了完整路径时不再重复拼。"""
    base = str(base_url or "").rstrip("/")
    if not base:
        raise ExplainerError("接口地址为空")
    if base.endswith(suffix):
        return base
    return base + suffix


def call_model(prompt: str, cfg: dict[str, str], timeout: int = 120,
               transport: Optional[Callable[[str, dict[str, str], dict[str, Any], float],
                                          tuple[int, str]]] = None) -> tuple[str, dict[str, Any]]:
    """调用大模型, 返回 (讲解正文, usage)。

    cfg 里的 protocol 决定接口形状:
      anthropic -> POST {base}/v1/messages, 头 x-api-key + anthropic-version
      openai    -> POST {base}/chat/completions, 头 Authorization: Bearer

    密钥只放在请求头里, 任何出现在错误信息里的密钥都会被 _redact 抹掉。
    """
    cfg = cfg or {}
    protocol = str(cfg.get("protocol") or PROTOCOL_ANTHROPIC).strip().lower()
    base_url = str(cfg.get("base_url") or "").rstrip("/")
    api_key = str(cfg.get("api_key") or "").strip()
    model = str(cfg.get("model") or DEFAULT_MODEL).strip()
    if protocol not in (PROTOCOL_ANTHROPIC, PROTOCOL_OPENAI):
        raise ExplainerError("不支持的接口协议: " + protocol)
    if not api_key:
        raise ExplainerError(
            "缺少模型 API Key：未找到环境变量 " + str(cfg.get("key_env") or API_KEY_ENV) + "。"
        )
    if protocol == PROTOCOL_OPENAI:
        url = _endpoint(base_url, "/chat/completions")
        headers = {
            "Authorization": "Bearer " + api_key,
            "content-type": "application/json",
        }
    else:
        url = _endpoint(base_url, "/v1/messages")
        headers = {
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
    body = {
        "model": model,
        "max_tokens": int(cfg.get("max_tokens") or DEFAULT_MAX_TOKENS),
        "messages": [{"role": "user", "content": prompt}],
    }
    call = transport or _default_transport
    status, text = call(url, headers, body, float(timeout))
    if status != 200:
        raise ExplainerError(
            "模型接口返回 HTTP " + str(status) + ": " + _redact(str(text)[:300], api_key)
        )
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ExplainerError(
            "模型返回的不是合法 JSON: " + _redact(str(text)[:300], api_key)
        ) from exc
    if not isinstance(data, dict):
        raise ExplainerError("模型返回的 JSON 不是对象")
    usage_raw = data.get("usage") or {}
    if protocol == PROTOCOL_OPENAI:
        choices = data.get("choices") or []
        content = ""
        if choices and isinstance(choices[0], dict):
            message = choices[0].get("message") or {}
            if isinstance(message, dict):
                content = str(message.get("content") or "")
        if not content.strip():
            raise ExplainerError("模型返回了空内容")
        usage = {
            "input_tokens": usage_raw.get("prompt_tokens"),
            "output_tokens": usage_raw.get("completion_tokens"),
            "total_tokens": usage_raw.get("total_tokens"),
        }
        return content.strip(), usage
    parts: list[str] = []
    for chunk in data.get("content") or []:
        if isinstance(chunk, dict) and chunk.get("type") == "text" and chunk.get("text"):
            parts.append(str(chunk["text"]))
    if not parts:
        raise ExplainerError("模型返回了空内容")
    usage = {
        "input_tokens": usage_raw.get("input_tokens"),
        "output_tokens": usage_raw.get("output_tokens"),
        "total_tokens": usage_raw.get("total_tokens"),
    }
    return "".join(parts).strip(), usage


# 旧名保留下来, 外部脚本按老名字调用也不会断
call_minimax = call_model


# --------------------------------------------------------------------------
# 洛谷题目抓取
# --------------------------------------------------------------------------

def _http_get(url: str, headers: dict[str, str], timeout: float) -> tuple[int, str]:
    try:
        import requests  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - 环境问题
        raise ExplainerError("缺少依赖 requests, 请先 pip install requests") from exc
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
    except requests.exceptions.Timeout as exc:
        raise ExplainerError("请求洛谷超时 (" + str(timeout) + "s)") from exc
    except requests.exceptions.RequestException as exc:
        raise ExplainerError("请求洛谷失败: " + type(exc).__name__ + ": " + str(exc)) from exc
    return resp.status_code, resp.text or ""


def _http_post(url: str, headers: dict[str, str], body: dict[str, Any],
               timeout: float) -> tuple[int, str]:
    try:
        import requests  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - 环境问题
        raise ExplainerError("缺少依赖 requests, 请先 pip install requests") from exc
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=timeout)
    except requests.exceptions.Timeout as exc:
        raise ExplainerError("请求洛谷超时 (" + str(timeout) + "s)") from exc
    except requests.exceptions.RequestException as exc:
        raise ExplainerError("请求洛谷失败: " + type(exc).__name__ + ": " + str(exc)) from exc
    return resp.status_code, resp.text or ""


_SECTION_TITLE_RE = re.compile(
    r'<div[^>]*class="[^"]*section-title[^"]*"[^>]*>(.*?)</div>', re.S | re.I)


def _split_html_sections(html_text: str) -> dict[str, str]:
    """把洛谷题面 HTML 按小节标题切开, 返回 {小节名: 纯文本}。"""
    marks = list(_SECTION_TITLE_RE.finditer(html_text or ""))
    sections: dict[str, str] = {}
    for index, mark in enumerate(marks):
        head = strip_html(mark.group(1)).strip()
        name = head.split()[0] if head else ""
        end = marks[index + 1].start() if index + 1 < len(marks) else len(html_text)
        body = strip_html(html_text[mark.end():end])
        if name and name not in sections:
            sections[name] = body
    return sections


def _extract_samples(html_fragment: str) -> list[dict[str, str]]:
    """从样例区 HTML 里粗略提取输入/输出对 (pre 标签成对出现)。"""
    blocks = [strip_html(m) for m in
              re.findall(r"<pre[^>]*>(.*?)</pre>", html_fragment or "", re.S | re.I)]
    blocks = [b for b in blocks if b.strip()]
    samples: list[dict[str, str]] = []
    for index in range(0, len(blocks) - 1, 2):
        samples.append({"input": blocks[index], "output": blocks[index + 1]})
    return samples


def parse_problem_html(pid: str, html_text: str) -> dict[str, Any]:
    """解析 GET /problem/{pid}?_contentOnly=1 返回的 HTML。"""
    text = html_text or ""
    title = ""
    match = re.search(r'<h1[^>]*class="[^"]*header[^"]*"[^>]*>(.*?)</h1>', text, re.S)
    if not match:
        match = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.S)
    if match:
        title = strip_html(match.group(1)).strip()
    if not title:
        match = re.search(r"<title>(.*?)</title>", text, re.S)
        if match:
            title = strip_html(match.group(1)).strip()
    title = re.sub(r"\s*[-_|]\s*洛谷.*$", "", title).strip() or pid

    difficulty = ""
    match = re.search(r'class="[^"]*difficulty[^"]*"[^>]*>(.*?)<', text, re.S)
    if match:
        difficulty = strip_html(match.group(1)).strip()
    if not difficulty:
        match = re.search(r"""difficulty["']?\s*[:=]\s*["']?(\d)""", text)
        if match:
            difficulty = DIFFICULTY_NAMES.get(int(match.group(1)), match.group(1))

    tags: list[str] = []
    for raw in re.findall(r"""/problem/list\?tag=([^"'&\s]+)""", text):
        tag = unquote_plus(raw).strip()
        if tag and tag not in tags:
            tags.append(tag)

    sections = _split_html_sections(text)
    ordered = ("题目描述", "输入格式", "输出格式", "说明/提示", "说明提示", "提示",
               "输入输出样例", "样例输入输出")
    parts: list[str] = []
    for key in ordered:
        if key in sections and sections[key].strip():
            parts.append("### " + key + "\n" + sections[key].strip())
    if not parts:
        statement = re.search(
            r'<section[^>]*class="[^"]*problem-statement[^"]*"[^>]*>(.*?)</section>',
            text, re.S | re.I)
        if statement:
            parts.append(strip_html(statement.group(1)))
    content = "\n\n".join(parts).strip()

    sample_source = sections.get("输入输出样例", "") or sections.get("样例输入输出", "")
    samples = _extract_samples(sample_source)
    return {
        "title": title,
        "difficulty": difficulty,
        "tags": tags,
        "content": content,
        "samples": samples,
    }


def parse_detail_json(pid: str, payload: Any) -> dict[str, Any]:
    """解析 POST /fe/api/problem/detail/{pid} 返回的 JSON。"""
    if not isinstance(payload, dict):
        return {}
    problem = payload.get("problem")
    if not isinstance(problem, dict):
        current = payload.get("currentData")
        problem = current.get("problem") if isinstance(current, dict) else None
    if not isinstance(problem, dict):
        problem = {}
    title = str(problem.get("title") or problem.get("fullTitle") or pid)
    raw_difficulty = problem.get("difficulty")
    difficulty = ""
    if raw_difficulty is not None:
        try:
            difficulty = DIFFICULTY_NAMES.get(int(raw_difficulty), str(raw_difficulty))
        except (TypeError, ValueError):
            difficulty = str(raw_difficulty)
    tags: list[str] = []
    for tag in problem.get("tags") or []:
        if isinstance(tag, (str, int)):
            text = str(tag).strip()
            if text and text not in tags:
                tags.append(text)
    blocks: list[str] = []
    description = strip_html(problem.get("content") or "")
    if description:
        blocks.append(description)
    for key, label in (("formatInput", "输入格式"), ("formatOutput", "输出格式"),
                       ("hint", "说明/提示")):
        chunk = strip_html(problem.get(key) or "")
        if chunk:
            blocks.append("### " + label + "\n" + chunk)
    samples: list[dict[str, str]] = []
    for sample in problem.get("samples") or []:
        if isinstance(sample, dict):
            samples.append({
                "input": str(sample.get("input", "")),
                "output": str(sample.get("output", "")),
            })
    return {
        "title": title,
        "difficulty": difficulty,
        "tags": tags,
        "content": "\n\n".join(blocks).strip(),
        "samples": samples,
    }


def fetch_problem(pid: str, cookie: Optional[str] = None, timeout: int = 20) -> dict[str, Any]:
    """抓取洛谷题目: 先试页面接口, 再试详情接口; 都拿不到就抛带登录提示的错误。"""
    normalized = normalize_pid(pid)
    if not normalized:
        raise ExplainerError("题号格式不正确, 例如 P1001")
    cookie_value = load_luogu_cookie() if cookie is None else (cookie or "")
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": LUOGU_BASE + "/problem/" + normalized,
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    if cookie_value:
        headers["Cookie"] = cookie_value

    reasons: list[str] = []
    try:
        status, body = _http_get(PROBLEM_PAGE.format(pid=normalized), headers, float(timeout))
        if status == 200:
            parsed = parse_problem_html(normalized, body)
            if parsed.get("content"):
                return parsed
            reasons.append("GET /problem/" + normalized + "?_contentOnly=1 返回 200 但没解析到题面"
                           "(多半是未登录时的 SPA 空壳)")
        else:
            reasons.append("GET /problem/" + normalized + "?_contentOnly=1 返回 HTTP " + str(status))
    except ExplainerError as exc:
        reasons.append("GET /problem/" + normalized + "?_contentOnly=1 失败: " + str(exc))

    try:
        status, body = _http_post(PROBLEM_DETAIL_API.format(pid=normalized), headers, {}, float(timeout))
        if status == 200:
            try:
                parsed = parse_detail_json(normalized, json.loads(body))
            except ValueError:
                parsed = {}
                reasons.append("详情接口返回的不是合法 JSON")
            if parsed.get("content"):
                return parsed
            reasons.append("POST /fe/api/problem/detail/" + normalized + " 返回 200 但没解析到题面")
        else:
            reasons.append("POST /fe/api/problem/detail/" + normalized + " 返回 HTTP "
                           + str(status) + ": " + str(body)[:200].replace("\n", " "))
    except ExplainerError as exc:
        reasons.append("POST /fe/api/problem/detail/" + normalized + " 失败: " + str(exc))

    raise ExplainerError(LOGIN_REQUIRED_HINT + "（" + "；".join(reasons) + "）")


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------

def explain(target: str, style: str = "面向初学者", cookie: Optional[str] = None,
            model: Optional[str] = None, timeout: int = 120,
            config: Optional[dict[str, str]] = None,
            provider: Optional[str] = None,
            caller: Optional[Callable[..., tuple[str, dict[str, Any]]]] = None,
            fetcher: Optional[Callable[..., dict[str, Any]]] = None) -> dict[str, Any]:
    """讲解一道题。target 可以是题号, 也可以是粘贴的题面文本。"""
    started = time.time()
    text = (target or "").strip()
    if not text:
        raise ExplainerError("题目内容为空: 请填写题号 (如 P1001) 或直接粘贴题面")

    if classify_target(text) == "pid":
        fetch = fetcher or fetch_problem
        problem = fetch(text, cookie) or {}
        title = str(problem.get("title") or normalize_pid(text))
        problem_text = str(problem.get("content") or "")
        source = "luogu"
    else:
        problem_text = text
        title = title_from_text(text)
        source = "text"

    if not problem_text.strip():
        raise ExplainerError(LOGIN_REQUIRED_HINT)

    prompt = build_prompt(problem_text, style)
    cfg = dict(config) if config else resolve_config(provider=provider)
    if model:
        cfg["model"] = model
    call = caller or call_model
    markdown, usage = call(prompt, cfg, timeout)
    return {
        "ok": True,
        "title": title,
        "markdown": markdown,
        "usage": usage,
        "elapsed_ms": int((time.time() - started) * 1000),
        "source": source,
        "provider": str(cfg.get("provider") or ""),
        "model": str(cfg.get("model") or ""),
    }


# --------------------------------------------------------------------------
# 自检 (完全离线)
# --------------------------------------------------------------------------

@contextlib.contextmanager
def _env_patch(**overrides: Optional[str]):
    """临时改环境变量, 退出时还原。"""
    saved = {key: os.environ.get(key) for key in overrides}
    for key, value in overrides.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _selftest() -> int:
    """离线自检: 不发网络请求、不读注册表密钥、不需要洛谷账号。"""
    cases: list[tuple[str, Callable[[], None]]] = []

    def case(name: str):
        def deco(fn: Callable[[], None]) -> Callable[[], None]:
            cases.append((name, fn))
            return fn
        return deco

    @case("strip_html 去标签并保留文字")
    def _() -> None:
        assert strip_html("<p>输入 n 个整数</p>") == "输入 n 个整数"

    @case("strip_html 把块级标签换成换行")
    def _() -> None:
        out = strip_html("第一行<br/>第二行<div>第三行</div>")
        assert "\n" in out and "第一行" in out and "第三行" in out, out

    @case("strip_html 解码 HTML 实体")
    def _() -> None:
        assert strip_html("a &lt; b &amp;&amp; c &gt; d") == "a < b && c > d"

    @case("strip_html 压掉多余空白与空行")
    def _() -> None:
        assert strip_html("a   \n\n\n\nb") == "a\n\nb"

    @case("strip_html 去掉 script/style 内容")
    def _() -> None:
        out = strip_html("<script>var x=1;</script><style>p{}</style><p>正文</p>")
        assert "var x" not in out and "正文" in out, out

    @case("strip_html 空输入返回空串")
    def _() -> None:
        assert strip_html("") == "" and strip_html(None) == ""

    @case("build_prompt 含全部固定小节")
    def _() -> None:
        prompt = build_prompt("题目内容", "面向初学者")
        for name in REQUIRED_SECTIONS:
            assert name in prompt, name
        assert len(REQUIRED_SECTIONS) >= 6

    @case("build_prompt 含题面原文与风格")
    def _() -> None:
        prompt = build_prompt("给定 n 个整数，输出它们的和。", "冲刺提分")
        assert "给定 n 个整数，输出它们的和。" in prompt
        assert "冲刺提分" in prompt
        assert "Markdown" in prompt

    @case("classify_target 区分题号与题面")
    def _() -> None:
        assert classify_target("P1001") == "pid"
        assert classify_target("1001") == "pid"
        assert classify_target("给定 n 个整数，输出它们的和。") == "text"
        assert classify_target("") == "text"

    @case("normalize_pid 归一题号")
    def _() -> None:
        assert normalize_pid("1001") == "P1001"
        assert normalize_pid("p1001") == "P1001"
        assert normalize_pid("") == ""

    @case("登录提示文案点名两个环境变量")
    def _() -> None:
        assert "LUOGU_CLIENT_ID" in LOGIN_REQUIRED_HINT
        assert "LUOGU_UID" in LOGIN_REQUIRED_HINT

    @case("resolve_config 无密钥时报错且点名变量")
    def _() -> None:
        with _env_patch(**{API_KEY_ENV: None, BASE_URL_ENV: None, MODEL_ENV: None}):
            try:
                resolve_config(use_registry=False)
            except ExplainerError as exc:
                assert API_KEY_ENV in str(exc), str(exc)
                assert "MINIMAX_API_KEY" in str(exc), str(exc)
            else:
                raise AssertionError("应当抛 ExplainerError")

    @case("resolve_config 优先读环境变量")
    def _() -> None:
        with _env_patch(**{API_KEY_ENV: "fake-key", BASE_URL_ENV: "https://example.test/anthropic",
                           MODEL_ENV: "fake-model"}):
            cfg = resolve_config(use_registry=False)
        assert cfg["api_key"] == "fake-key"
        assert cfg["base_url"] == "https://example.test/anthropic"
        assert cfg["model"] == "fake-model"

    @case("config_snapshot 只暴露有没有密钥")
    def _() -> None:
        with _env_patch(**{API_KEY_ENV: "super-secret-key"}):
            snap = config_snapshot(use_registry=False)
        assert snap["has_key"] is True
        assert snap["base_url"].startswith("http")

    @case("call_minimax 非 200 时带出状态码且不含密钥")
    def _() -> None:
        def transport(url, headers, body, timeout):
            assert headers["x-api-key"] == "fake-key"
            return 500, '{"error":"boom"}'
        try:
            call_minimax("prompt", {"api_key": "fake-key", "base_url": "https://x.test",
                                    "model": "m"}, timeout=5, transport=transport)
        except ExplainerError as exc:
            assert "500" in str(exc), str(exc)
            assert "fake-key" not in str(exc), str(exc)
        else:
            raise AssertionError("应当抛 ExplainerError")

    @case("call_minimax 解析正文与 usage")
    def _() -> None:
        def transport(url, headers, body, timeout):
            assert url == "https://x.test/v1/messages"
            assert headers["anthropic-version"] == ANTHROPIC_VERSION
            return 200, json.dumps({
                "content": [{"type": "text", "text": "## 题目在考什么\n讲解"}],
                "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
            })
        text, usage = call_minimax("prompt", {"api_key": "fake-key", "base_url": "https://x.test",
                                               "model": "m"}, timeout=5, transport=transport)
        assert "题目在考什么" in text
        assert usage["total_tokens"] == 30

    @case("explain 对粘贴题面走本地路径 (source=text)")
    def _() -> None:
        calls: list = []

        def caller(prompt, cfg, timeout):
            calls.append((prompt, cfg))
            return "## 题目在考什么\n本地讲解", {"total_tokens": 7}

        result = explain("给定 n 个整数，输出它们的和。",
                         config={"api_key": "fake-key", "base_url": "https://x.test", "model": "m"},
                         caller=caller)
        assert result["ok"] is True
        assert result["source"] == "text"
        assert result["title"].startswith("给定 n 个整数")
        assert result["usage"]["total_tokens"] == 7
        assert result["elapsed_ms"] >= 0
        assert len(calls) == 1 and "给定 n 个整数" in calls[0][0]

    @case("explain 对题号走洛谷路径 (source=luogu)")
    def _() -> None:
        def fetcher(pid, cookie=None):
            assert pid == "P1001"
            return {"title": "A+B Problem", "difficulty": "入门", "tags": [],
                    "content": "输入 a, b, 输出 a+b", "samples": []}

        def caller(prompt, cfg, timeout):
            return "## 题目在考什么\n洛谷讲解", {"total_tokens": 3}

        result = explain("P1001",
                         config={"api_key": "fake-key", "base_url": "https://x.test", "model": "m"},
                         caller=caller, fetcher=fetcher)
        assert result["source"] == "luogu"
        assert result["title"] == "A+B Problem"

    @case("explain 空输入报错")
    def _() -> None:
        try:
            explain("   ", config={"api_key": "fake-key"}, caller=lambda *a: ("", {}))
        except ExplainerError as exc:
            assert "为空" in str(exc), str(exc)
        else:
            raise AssertionError("应当抛 ExplainerError")

    @case("parse_detail_json 解析题面与难度")
    def _() -> None:
        parsed = parse_detail_json("P1001", {
            "problem": {
                "title": "A+B Problem",
                "difficulty": 3,
                "tags": ["入门", "模拟"],
                "content": "<p>输入两个数</p>",
                "samples": [{"input": "1 2", "output": "3"}],
            }
        })
        assert parsed["title"] == "A+B Problem"
        assert parsed["difficulty"] == "普及"
        assert "输入两个数" in parsed["content"]
        assert parsed["samples"] == [{"input": "1 2", "output": "3"}]

    @case("parse_problem_html 解析标题与标签")
    def _() -> None:
        parsed = parse_problem_html("P1001", (
            '<h1 class="header">A+B Problem</h1>'
            '<a href="/problem/list?tag=%E6%A8%A1%E6%8B%9F">模拟</a>'
            '<div class="section-title"><span class="section-title__cn">题目描述</span></div>'
            '<p>输入两个整数</p>'
            '<div class="section-title"><span class="section-title__cn">输入格式</span></div>'
            '<p>两个整数</p>'
        ))
        assert parsed["title"] == "A+B Problem"
        assert parsed["tags"] == ["模拟"]
        assert "输入两个整数" in parsed["content"]
        assert "输入格式" in parsed["content"]

    @case("_redact 抹掉密钥")
    def _() -> None:
        assert "s3cr3t" not in _redact("key=s3cr3t&x=1", "s3cr3t")

    @case("提示词模板文件可加载且字段齐全")
    def _() -> None:
        template = load_prompt_template()
        assert template["required_sections"], template
        assert "{{sections}}" in template["user_prompt_template"]
        assert "{{problem}}" in template["user_prompt_template"]
        assert "{{style}}" in template["user_prompt_template"]
        assert "面向初学者" in template["styles"]

    @case("提示词模板与 REQUIRED_SECTIONS 是同一份定义")
    def _() -> None:
        template = load_prompt_template()
        assert tuple(template["required_sections"]) == tuple(REQUIRED_SECTIONS)

    @case("build_prompt 不留未替换的占位符")
    def _() -> None:
        prompt = build_prompt("给定 n 个整数, 输出它们的和。", "冲刺提分")
        assert "{{" not in prompt, prompt
        assert "冲刺提分" in prompt
        assert "给定 n 个整数, 输出它们的和。" in prompt

    @case("模型预设表可加载且字段齐全")
    def _() -> None:
        table = load_providers()
        assert table["providers"], table
        assert table["protocols"], table
        for spec in table["providers"]:
            assert spec["id"] and spec["label"] and spec["protocol"], spec
            assert spec["key_env"], spec

    @case("默认厂商在预设表里")
    def _() -> None:
        table = load_providers()
        ids = [str(s["id"]) for s in table["providers"]]
        assert str(table["default_provider"]) in ids, ids

    @case("厂商预设只引用已知协议")
    def _() -> None:
        table = load_providers()
        known = set(table["protocols"])
        for spec in table["providers"]:
            assert str(spec["protocol"]) in known, spec

    @case("find_provider 未知 id 时报错并列出可选")
    def _() -> None:
        try:
            find_provider("no-such-vendor")
        except ExplainerError as exc:
            assert "no-such-vendor" in str(exc), str(exc)
            assert "minimax" in str(exc), str(exc)
        else:
            raise AssertionError("应当抛 ExplainerError")

    @case("resolve_config 按厂商读对应环境变量")
    def _() -> None:
        with _env_patch(**{"DEEPSEEK_API_KEY": "ds-key", "DEEPSEEK_BASE_URL": None,
                           "DEEPSEEK_MODEL": None, API_KEY_ENV: None}):
            cfg = resolve_config(provider="deepseek", use_registry=False)
        assert cfg["api_key"] == "ds-key"
        assert cfg["protocol"] == "openai"
        assert cfg["provider"] == "deepseek"
        assert cfg["base_url"] == "https://api.deepseek.com", cfg
        assert cfg["model"] == "deepseek-chat", cfg

    @case("resolve_config 缺厂商密钥时报错并点名变量")
    def _() -> None:
        with _env_patch(**{"MOONSHOT_API_KEY": None, API_KEY_ENV: None}):
            try:
                resolve_config(provider="moonshot", use_registry=False)
            except ExplainerError as exc:
                assert "MOONSHOT_API_KEY" in str(exc), str(exc)
            else:
                raise AssertionError("应当抛 ExplainerError")

    @case("自定义厂商走 LLM_API_KEY")
    def _() -> None:
        with _env_patch(**{"LLM_API_KEY": "custom-key",
                           "LLM_BASE_URL": "http://127.0.0.1:11434/v1",
                           "LLM_MODEL": "qwen2.5:7b", API_KEY_ENV: None}):
            cfg = resolve_config(provider="custom", use_registry=False)
        assert cfg["api_key"] == "custom-key"
        assert cfg["base_url"] == "http://127.0.0.1:11434/v1"
        assert cfg["model"] == "qwen2.5:7b"

    @case("call_model anthropic 协议请求形状正确")
    def _() -> None:
        def transport(url, headers, body, timeout):
            assert url == "https://x.test/v1/messages", url
            assert headers["x-api-key"] == "fake-key"
            assert headers["anthropic-version"] == ANTHROPIC_VERSION
            assert body["model"] == "m"
            return 200, json.dumps({"content": [{"type": "text", "text": "讲解"}],
                                     "usage": {"input_tokens": 1, "output_tokens": 2}})
        text, usage = call_model("prompt", {"api_key": "fake-key", "base_url": "https://x.test",
                                            "model": "m", "protocol": "anthropic"},
                                 timeout=5, transport=transport)
        assert text == "讲解"
        assert usage["input_tokens"] == 1 and usage["output_tokens"] == 2

    @case("call_model openai 协议请求形状与解析")
    def _() -> None:
        def transport(url, headers, body, timeout):
            assert url == "https://x.test/chat/completions", url
            assert headers["Authorization"] == "Bearer fake-key", headers
            assert "x-api-key" not in headers
            assert body["messages"][0]["content"] == "prompt"
            return 200, json.dumps({"choices": [{"message": {"content": "## 讲解\n正文"}}],
                                     "usage": {"prompt_tokens": 5, "completion_tokens": 6,
                                               "total_tokens": 11}})
        text, usage = call_model("prompt", {"api_key": "fake-key", "base_url": "https://x.test",
                                            "model": "m", "protocol": "openai"},
                                 timeout=5, transport=transport)
        assert "讲解" in text
        assert usage["input_tokens"] == 5
        assert usage["output_tokens"] == 6
        assert usage["total_tokens"] == 11

    @case("call_model 未知协议时报错")
    def _() -> None:
        try:
            call_model("prompt", {"api_key": "k", "base_url": "https://x.test",
                                   "model": "m", "protocol": "grpc"}, timeout=5,
                       transport=lambda *a: (200, "{}"))
        except ExplainerError as exc:
            assert "grpc" in str(exc), str(exc)
        else:
            raise AssertionError("应当抛 ExplainerError")

    @case("call_model 缺密钥时报错并点名环境变量")
    def _() -> None:
        try:
            call_model("prompt", {"base_url": "https://x.test", "model": "m",
                                   "protocol": "openai", "key_env": "DEEPSEEK_API_KEY"},
                       timeout=5, transport=lambda *a: (200, "{}"))
        except ExplainerError as exc:
            assert "DEEPSEEK_API_KEY" in str(exc), str(exc)
        else:
            raise AssertionError("应当抛 ExplainerError")

    @case("call_model 非 200 时报错且不含密钥")
    def _() -> None:
        try:
            call_model("prompt", {"api_key": "fake-key", "base_url": "https://x.test",
                                   "model": "m", "protocol": "openai"}, timeout=5,
                       transport=lambda url, headers, body, timeout: (401, '{"error":"bad key"}'))
        except ExplainerError as exc:
            assert "401" in str(exc), str(exc)
            assert "fake-key" not in str(exc), str(exc)
        else:
            raise AssertionError("应当抛 ExplainerError")

    @case("_endpoint 不重复拼已经写全的路径")
    def _() -> None:
        assert _endpoint("https://x.test", "/v1/messages") == "https://x.test/v1/messages"
        assert _endpoint("https://x.test/v1/messages", "/v1/messages") == "https://x.test/v1/messages"
        assert _endpoint("https://x.test/", "/chat/completions") == "https://x.test/chat/completions"

    @case("自定义厂商的地址与模型留空交给用户填")
    def _() -> None:
        spec = find_provider("custom")
        assert spec["base_url"] == "", spec
        assert spec["model"] == "", spec

    passed = 0
    failed = 0
    print("洛谷题目自动讲解 离线自检")
    print("-" * 46)
    for name, fn in cases:
        try:
            fn()
        except AssertionError as exc:
            failed += 1
            print("  [FAIL] " + name + ": " + str(exc))
        except Exception as exc:
            failed += 1
            print("  [ERROR] " + name + ": " + type(exc).__name__ + ": " + str(exc))
        else:
            passed += 1
            print("  [PASS] " + name)
    print("-" * 46)
    print("自检结果: " + str(passed) + " passed / " + str(failed) + " failed")
    return 0 if failed == 0 else 1


# --------------------------------------------------------------------------
# 命令行
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="洛谷题目自动讲解 (面向自学/教学)")
    ap.add_argument("--pid", help="题号, 例如 P1001")
    ap.add_argument("--file", help="已保存的题面文本文件 (UTF-8)")
    ap.add_argument("--out", help="把讲解写入的 Markdown 文件")
    ap.add_argument("--style", default="面向初学者", help="讲解风格, 默认 面向初学者")
    ap.add_argument("--model", help="覆盖模型名")
    ap.add_argument("--provider", help="模型厂商 id, 见 explainer/providers.json (默认 minimax)")
    ap.add_argument("--timeout", type=int, default=120, help="调用超时秒数, 默认 120")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    ap.add_argument("--selftest", action="store_true", help="离线自检, 不联网")
    return ap


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)

    if args.selftest:
        return _selftest()

    target = ""
    if args.pid:
        target = args.pid
    elif args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as handle:
                target = handle.read()
        except OSError as exc:
            print("[读取失败] " + str(exc), file=sys.stderr)
            return 2
    else:
        print("请用 --pid 指定题号, 或用 --file 指定题面文件", file=sys.stderr)
        return 2

    try:
        result = explain(target, style=args.style, model=args.model,
                         provider=args.provider, timeout=args.timeout)
    except ExplainerError as exc:
        print("[讲解失败] " + str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n已中断", file=sys.stderr)
        return 130

    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as handle:
                handle.write(result["markdown"])
        except OSError as exc:
            print("[写入失败] " + str(exc), file=sys.stderr)
            return 2
        print("已写入 " + args.out + " (" + result["title"] + ", " + str(result["elapsed_ms"]) + " ms)")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif not args.out:
        print(result["markdown"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
