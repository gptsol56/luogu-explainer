# -*- coding: utf-8 -*-
"""
server/app.py - 洛谷讲解助手的本地 API + 静态站点服务

只用标准库 (http.server.ThreadingHTTPServer), 不引入 fastapi / uvicorn / flask。
默认只监听 127.0.0.1, 不对外网暴露。

接口:
    GET  /api/health            健康检查 (只暴露"有没有密钥", 绝不返回密钥本身)
    GET  /api/problem/{pid}      抓洛谷题目
    POST /api/explain            讲解 (pid 或 text)
    POST /api/punch              调仓库根的 luogu_punch 打一次卡
    GET  /prompt_template.json   提示词模板 (与 explainer 读的是同一份文件)
    GET  /...                    web/ 下的静态文件 (挡住路径穿越)

用法:
    python server/app.py --host 127.0.0.1 --port 8848
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote, urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = REPO_ROOT / "web"
PROMPT_TEMPLATE_PATH = REPO_ROOT / "explainer" / "prompt_template.json"
VERSION = "1.0.0"
MAX_BODY_BYTES = 2 * 1024 * 1024

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}


def _load_module(name: str, path: Path):
    """按文件路径加载模块, 不依赖当前工作目录, 也不需要是包。"""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载模块: " + str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


explainer = _load_module("luogu_explainer", REPO_ROOT / "explainer" / "luogu_explainer.py")
punch = _load_module("luogu_punch", REPO_ROOT / "luogu_punch.py")


def _safe_join(base: Path, relative: str) -> Optional[Path]:
    """把相对路径拼到 base 下, 并挡住路径穿越。越界返回 None。"""
    if not relative:
        return None
    cleaned = relative.replace("\\", "/")
    parts = [p for p in cleaned.split("/") if p not in ("", ".", "..")]
    if not parts:
        return None
    base_resolved = base.resolve()
    target = (base_resolved / Path(*parts)).resolve()
    if target != base_resolved and base_resolved not in target.parents:
        return None
    return target


class Handler(BaseHTTPRequestHandler):
    server_version = "LuoguExplainer/" + VERSION
    protocol_version = "HTTP/1.1"

    # ---------------- 基础工具 ----------------

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        sys.stderr.write("[server] " + (fmt % args) + "\n")

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, message: str, status: int = 200) -> None:
        self._send_json({"ok": False, "error": str(message)}, status)

    def _read_json_body(self) -> Optional[dict[str, Any]]:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            length = 0
        if length <= 0:
            return {}
        if length > MAX_BODY_BYTES:
            self._send_error_json("请求体过大")
            return None
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._send_error_json("请求体不是合法 JSON")
            return None
        if not isinstance(data, dict):
            self._send_error_json("请求体必须是 JSON 对象")
            return None
        return data

    # ---------------- 路由 ----------------

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path == "/api/health":
                return self._handle_health()
            if path.startswith("/api/problem/"):
                return self._handle_problem(path[len("/api/problem/"):])
            if path == "/prompt_template.json":
                return self._serve_prompt_template()
            if path.startswith("/api/"):
                return self._send_error_json("未知接口: " + path, status=404)
            return self._serve_static(path)
        except Exception as exc:  # noqa: BLE001 - 兜底, 不把堆栈泄给前端
            traceback.print_exc()
            return self._send_error_json("服务端异常: " + type(exc).__name__)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path == "/api/explain":
                return self._handle_explain()
            if path == "/api/punch":
                return self._handle_punch()
            return self._send_error_json("未知接口: " + path, status=404)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return self._send_error_json("服务端异常: " + type(exc).__name__)

    # ---------------- 各接口实现 ----------------

    def _handle_health(self) -> None:
        snapshot = explainer.config_snapshot()
        base_host = urlparse(str(snapshot.get("base_url") or "")).netloc
        punch_ready = bool((os.environ.get(explainer.CLIENT_ID_ENV) or "").strip()
                           and (os.environ.get(explainer.UID_ENV) or "").strip())
        self._send_json({
            "ok": True,
            "model": snapshot.get("model"),
            "base_host": base_host,
            "has_key": bool(snapshot.get("has_key")),
            "punch_ready": punch_ready,
            "version": VERSION,
        })

    def _handle_problem(self, raw_pid: str) -> None:
        pid = unquote(raw_pid).strip()
        if not pid:
            return self._send_error_json("缺少题号")
        try:
            problem = explainer.fetch_problem(pid)
        except explainer.ExplainerError as exc:
            return self._send_error_json(str(exc))
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return self._send_error_json("抓取题目失败: " + type(exc).__name__)
        self._send_json({
            "ok": True,
            "title": problem.get("title"),
            "difficulty": problem.get("difficulty"),
            "tags": problem.get("tags") or [],
            "content": problem.get("content") or "",
            "samples": problem.get("samples") or [],
        })

    def _handle_explain(self) -> None:
        body = self._read_json_body()
        if body is None:
            return
        pid = str(body.get("pid") or "").strip()
        text = str(body.get("text") or "").strip()
        style = str(body.get("style") or "面向初学者").strip() or "面向初学者"
        target = pid or text
        if not target:
            return self._send_error_json("请填写题号 (pid) 或粘贴题面 (text)")
        try:
            result = explainer.explain(target, style=style)
        except explainer.ExplainerError as exc:
            return self._send_error_json(str(exc))
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return self._send_error_json("讲解失败: " + type(exc).__name__)
        self._send_json({
            "ok": True,
            "title": result.get("title"),
            "markdown": result.get("markdown") or "",
            "usage": result.get("usage") or {},
            "elapsed_ms": result.get("elapsed_ms"),
            "source": result.get("source"),
        })

    def _handle_punch(self) -> None:
        try:
            creds = punch.load_credentials()
        except punch.PunchError as exc:
            return self._send_json({
                "ok": False,
                "code": None,
                "message": str(exc),
                "elapsed_ms": 0,
            })
        try:
            result = punch.punch_once(creds)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            return self._send_json({
                "ok": False,
                "code": None,
                "message": "打卡请求失败: " + type(exc).__name__,
                "elapsed_ms": 0,
            })
        ok = bool(result.ok)
        # 201 的语义有歧义, 必须结合 message 判定 (与 luogu_punch.interpret 保持一致)
        if int(result.code) == 201 and any(
                hint in (result.message or "") for hint in ("请登录", "未登录", "登录后")):
            ok = False
        self._send_json({
            "ok": ok,
            "code": result.code,
            "message": result.message,
            "elapsed_ms": result.elapsed_ms,
        })


    # ---------------- 提示词模板 ----------------

    def _serve_prompt_template(self) -> None:
        """发提示词模板。浏览器端与 explainer 读的是同一个文件, 提示词因此只有一份。"""
        try:
            body = PROMPT_TEMPLATE_PATH.read_bytes()
        except OSError:
            return self._send_error_json("提示词模板不存在", status=404)
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # ---------------- 静态文件 ----------------

    def _serve_static(self, path: str) -> None:
        relative = unquote(path).lstrip("/") or "index.html"
        if relative == "":
            relative = "index.html"
        target = _safe_join(WEB_DIR, relative)
        if target is None:
            return self._send_error_json("非法路径", status=403)
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            return self._send_error_json("文件不存在: " + relative, status=404)
        content_type = CONTENT_TYPES.get(target.suffix.lower(), "application/octet-stream")
        try:
            body = target.read_bytes()
        except OSError:
            return self._send_error_json("读取文件失败", status=500)
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="洛谷讲解助手本地服务")
    ap.add_argument("--host", default="127.0.0.1", help="监听地址, 默认 127.0.0.1")
    ap.add_argument("--port", type=int, default=8848, help="监听端口, 默认 8848")
    args = ap.parse_args(argv)

    if not WEB_DIR.is_dir():
        print("[警告] 找不到前端目录: " + str(WEB_DIR), file=sys.stderr)

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    httpd.daemon_threads = True
    url = "http://" + args.host + ":" + str(args.port) + "/"
    print("洛谷题目自动讲解服务已启动: " + url)
    print("  题目讲解   : " + url + " (标签页①)")
    print("  打卡与本机服务: " + url + " (标签页②)")
    print("按 Ctrl+C 停止。")
    sys.stdout.flush()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n正在停止服务……")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
