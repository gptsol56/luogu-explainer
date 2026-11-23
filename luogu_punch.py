# -*- coding: utf-8 -*-
"""
luogu_punch.py - 洛谷每日打卡助手

用途: 调用洛谷 /index/ajax_punch 完成每日打卡, 保住连续签到天数。

设计原则:
  1. 凭据只从环境变量读, 绝不硬编码、绝不写进配置文件、绝不进版本库;
  2. 所有网络调用都有超时与重试(指数退避), 失败给出可执行的排查建议;
  3. 自带 --selftest, 不碰网络也能验证各项逻辑 (适合放进 CI);
  4. 返回码语义有歧义时以服务端 message 为准, 不靠猜。

用法:
    python luogu_punch.py                 # 一次性打卡
    python luogu_punch.py --json          # 一次性打卡 (JSON 输出)
    python luogu_punch.py --schedule      # 每天 10:00 定时打卡 (北京时间)
    python luogu_punch.py --selftest      # 不联网自检

凭据准备 (环境变量):
    setx LUOGU_CLIENT_ID  <你的 __client_id>
    setx LUOGU_UID       <你的 _uid>
获取方式: 浏览器登录 luogu.com.cn -> F12 -> Application -> Cookie -> https://luogu.com.cn
注意: setx 只对之后新开的进程生效, 当前终端需重开。

退出码:
    0  打卡成功 (含"今日已打卡")
    1  打卡失败
    2  凭据 / 参数配置错误
    130 被 Ctrl+C 中断
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional, Tuple

PUNCH_URL = "https://www.luogu.com.cn/index/ajax_punch"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
CLIENT_ID_ENV = "LUOGU_CLIENT_ID"
UID_ENV = "LUOGU_UID"
DEFAULT_TIMEOUT = 15
DEFAULT_RETRIES = 3
DEFAULT_AT = "10:00"

# 洛谷返回 code=201 时有两种含义(实测与上游实现不一致), 用 message 兜底判定:
#   "请登录洛谷进行打卡, 获得今日运势。" -> 未登录, 凭据无效
#   其他                                   -> 今日已打卡
NOT_LOGGED_IN_HINTS = ("请登录", "未登录", "登录后", "未登陆", "login")


class PunchError(RuntimeError):
    """打卡过程中的可预期错误。"""


@dataclass
class Credentials:
    client_id: str
    uid: str

    @property
    def cookie(self) -> str:
        return f"__client_id={self.client_id}; _uid={self.uid};"


@dataclass
class PunchResult:
    ok: bool
    code: int
    message: str
    raw: str = ""
    elapsed_ms: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


def load_credentials() -> Credentials:
    """从环境变量读取凭据。缺失时抛出带修复指引的 PunchError。"""
    client_id = os.environ.get(CLIENT_ID_ENV, "").strip()
    uid = os.environ.get(UID_ENV, "").strip()
    missing = []
    if not client_id:
        missing.append(CLIENT_ID_ENV)
    if not uid:
        missing.append(UID_ENV)
    if missing:
        raise PunchError(
            "缺少环境变量: " + ", ".join(missing)
            + "\n请先设置 (PowerShell): setx " + CLIENT_ID_ENV + " <你的 __client_id> ; setx " + UID_ENV + " <你的 _uid>"
            + "\n获取方式: 浏览器登录 luogu.com.cn -> F12 -> Application -> Cookie -> https://luogu.com.cn"
        )
    if not client_id.isalnum():
        raise PunchError(CLIENT_ID_ENV + " 含有非字母数字字符, 请确认复制完整")
    if not uid.isdigit():
        raise PunchError(UID_ENV + " 应该是纯数字, 请确认复制完整")
    return Credentials(client_id=client_id, uid=uid)


def build_headers(creds: Credentials) -> dict[str, str]:
    return {"Cookie": creds.cookie, "User-Agent": USER_AGENT, "Referer": "https://www.luogu.com.cn/"}


def interpret(payload: dict[str, Any]) -> tuple[bool, str]:
    """把洛谷返回体翻译成 (是否成功, 人话说明)。"""
    code = int(payload.get("code", -1))
    msg = str(payload.get("message", "")).strip()
    low = msg.lower()
    not_logged_in = any(h in msg or h in low for h in NOT_LOGGED_IN_HINTS)
    if code == 200:
        return True, msg or "打卡成功"
    if code == 201:
        if not_logged_in:
            return False, msg or "未登录洛谷, 凭据无效, 请重新从浏览器 Cookie 复制 __client_id 与 _uid"
        return True, msg or "今日已打卡, 无需重复打卡"
    if code in (401, 403):
        return False, msg or "凭据无效或已过期, 请重新从浏览器 Cookie 复制 __client_id 与 _uid"
    if code == 429:
        return False, msg or "请求过于频繁, 稍后再试"
    return False, msg or f"未知返回码 {code}"


def _default_transport(url: str, headers: dict[str, str], timeout: float) -> tuple[int, str]:
    """真实 HTTP GET。requests 延迟导入, 让 --selftest 在没装依赖时也能跑。"""
    import requests  # noqa: PLC0415  (延迟导入是刻意的)

    resp = requests.get(url, headers=headers, timeout=timeout)
    return resp.status_code, resp.text


def punch_once(
    creds: Credentials,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    transport: Optional[Callable[[str, dict[str, str], float], tuple[int, str]]] = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> PunchResult:
    """打卡一次。网络异常 / 5xx / 429 会按指数退避重试。"""
    transport = transport or _default_transport
    headers = build_headers(creds)
    attempts = max(1, int(retries))
    started = time.time()
    last_error = ""

    for attempt in range(1, attempts + 1):
        status = 0
        text = ""
        payload: Optional[dict[str, Any]] = None
        try:
            status, text = transport(PUNCH_URL, headers, timeout)
        except Exception as exc:  # 网络层异常: 值得重试
            last_error = f"{type(exc).__name__}: {exc}"
        else:
            try:
                parsed = json.loads(text)
            except Exception:
                last_error = "响应不是合法 JSON: " + repr(text[:120])
            else:
                if isinstance(parsed, dict):
                    payload = parsed
                else:
                    last_error = "响应 JSON 不是对象: " + repr(text[:120])

        code = -1
        if payload is not None:
            try:
                code = int(payload.get("code", -1))
            except (TypeError, ValueError):
                code = -1

        retryable = payload is None or code == 429 or status >= 500
        if retryable and attempt < attempts:
            delay = min(2 ** (attempt - 1), 8) + random.uniform(0, 0.5)
            sleeper(delay)
            continue

        elapsed_ms = int((time.time() - started) * 1000)
        extra = {"attempts": attempt, "status": status, "last_error": last_error}
        if payload is None:
            return PunchResult(False, -1, last_error or "打卡请求失败", text[:500], elapsed_ms, extra)
        ok, message = interpret(payload)
        return PunchResult(ok, code, message, text[:500], elapsed_ms, extra)

    # 理论不可达: 循环内要么 return 要么 continue
    return PunchResult(False, -1, last_error or "打卡请求失败", "", 0, {"attempts": attempts})


def _shanghai_tz():
    """拿到 Asia/Shanghai 时区。

    Windows 上 zoneinfo 常缺 tzdata, 依次回退 pytz, 最后退到固定 UTC+8
    (中国自 1991 年起不再使用夏令时, 对当前日期而言固定偏移是精确的)。
    """
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo("Asia/Shanghai")
    except Exception:
        pass
    try:
        import pytz

        return pytz.timezone("Asia/Shanghai")
    except Exception:
        return timezone(timedelta(hours=8), "CST")


def _now_shanghai() -> datetime:
    return datetime.now(_shanghai_tz())


def _parse_at(at: str) -> tuple[int, int]:
    try:
        hour_s, minute_s = at.strip().split(":")
        hour, minute = int(hour_s), int(minute_s)
    except Exception:
        raise PunchError(f"时间格式应为 HH:MM, 收到: {at!r}") from None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise PunchError(f"时间超出范围: {at!r}")
    return hour, minute


def _next_run(now_local: datetime, hour: int, minute: int) -> datetime:
    """今天 HH:MM 还没到 -> 今天; 已经过了 -> 明天。"""
    target = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now_local:
        target = target + timedelta(days=1)
    return target


def punch_with_schedule(
    creds: Credentials,
    at: str = DEFAULT_AT,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    max_runs: Optional[int] = None,
    sleeper: Callable[[float], None] = time.sleep,
    runner: Optional[Callable[[], PunchResult]] = None,
    clock: Callable[[], datetime] = _now_shanghai,
) -> int:
    """常驻模式: 每天在 at (北京时间) 打卡一次。返回实际执行次数。"""
    if runner is None:
        runner = lambda: punch_once(creds, timeout=timeout, retries=retries)
    hour, minute = _parse_at(at)
    runs = 0
    while True:
        now = clock()
        nxt = _next_run(now, hour, minute)
        wait = max(0.0, (nxt - now).total_seconds())
        print(f"[{now:%Y-%m-%d %H:%M:%S}] 下次打卡: {nxt:%Y-%m-%d %H:%M:%S} (等待 {wait / 3600:.2f} 小时)", flush=True)
        sleeper(wait)
        result = runner()
        runs += 1
        stamp = clock()
        print(f"[{stamp:%Y-%m-%d %H:%M:%S}] 打卡结果: {'成功' if result.ok else '失败'} - {result.message}", flush=True)
        if max_runs is not None and runs >= max_runs:
            return runs


def run_once(
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    transport: Optional[Callable[[str, dict[str, str], float], tuple[int, str]]] = None,
) -> PunchResult:
    creds = load_credentials()
    return punch_once(creds, timeout=timeout, retries=retries, transport=transport)


@contextlib.contextmanager
def _env_patch(**overrides: Optional[str]):
    """临时改环境变量, 退出时还原。"""
    saved = {k: os.environ.get(k) for k in overrides}
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
    """离线自检: 不发任何网络请求, 覆盖凭据校验、返回码解释、重试与调度逻辑。"""
    cases: list[tuple[str, Callable[[], None]]] = []

    def case(name: str):
        def deco(fn: Callable[[], None]) -> Callable[[], None]:
            cases.append((name, fn))
            return fn

        return deco

    def fake_transport(payload: dict[str, Any], status: int = 200, calls: Optional[list] = None):
        def _t(url: str, headers: dict[str, str], timeout: float) -> tuple[int, str]:
            if calls is not None:
                calls.append((url, dict(headers), timeout))
            return status, json.dumps(payload, ensure_ascii=False)

        return _t

    @case("cookie 拼接格式正确")
    def _() -> None:
        c = Credentials(client_id="abc123", uid="456")
        assert c.cookie == "__client_id=abc123; _uid=456;", c.cookie

    @case("请求头包含 Cookie / User-Agent / Referer")
    def _() -> None:
        h = build_headers(Credentials("abc", "1"))
        assert set(h) == {"Cookie", "User-Agent", "Referer"}, h
        assert h["Cookie"] == "__client_id=abc; _uid=1;"

    @case("code 200 视为打卡成功")
    def _() -> None:
        ok, msg = interpret({"code": 200, "message": "打卡成功"})
        assert ok is True and msg == "打卡成功"

    @case("code 201 且 message 含请登录 -> 判为凭据失效")
    def _() -> None:
        ok, msg = interpret({"code": 201, "message": "请登录洛谷进行打卡，获得今日运势。"})
        assert ok is False, msg
        assert "请登录" in msg

    @case("code 201 且 message 不含登录 -> 判为今日已打卡")
    def _() -> None:
        ok, msg = interpret({"code": 201, "message": "今天已经打过卡啦"})
        assert ok is True, msg

    @case("code 201 无 message -> 判为今日已打卡")
    def _() -> None:
        ok, msg = interpret({"code": 201})
        assert ok is True and "已打卡" in msg

    @case("code 401 / 403 判为失败")
    def _() -> None:
        assert interpret({"code": 401})[0] is False
        assert interpret({"code": 403})[0] is False

    @case("code 429 判为请求频繁")
    def _() -> None:
        ok, msg = interpret({"code": 429})
        assert ok is False and "频繁" in msg

    @case("未知返回码不崩溃")
    def _() -> None:
        ok, msg = interpret({"code": 777})
        assert ok is False and "777" in msg

    @case("缺少 code 字段不崩溃")
    def _() -> None:
        ok, _ = interpret({})
        assert ok is False

    @case("缺凭据时报错且点名变量")
    def _() -> None:
        with _env_patch(**{CLIENT_ID_ENV: None, UID_ENV: None}):
            try:
                load_credentials()
            except PunchError as exc:
                assert CLIENT_ID_ENV in str(exc) and UID_ENV in str(exc), str(exc)
            else:
                raise AssertionError("应当抛 PunchError")

    @case("client_id 含非字母数字被拒")
    def _() -> None:
        with _env_patch(**{CLIENT_ID_ENV: "abc-123", UID_ENV: "456"}):
            try:
                load_credentials()
            except PunchError as exc:
                assert CLIENT_ID_ENV in str(exc), str(exc)
            else:
                raise AssertionError("应当抛 PunchError")

    @case("uid 非纯数字被拒")
    def _() -> None:
        with _env_patch(**{CLIENT_ID_ENV: "abc123", UID_ENV: "45a"}):
            try:
                load_credentials()
            except PunchError as exc:
                assert UID_ENV in str(exc), str(exc)
            else:
                raise AssertionError("应当抛 PunchError")

    @case("正常读取凭据且两端空格被裁掉")
    def _() -> None:
        with _env_patch(**{CLIENT_ID_ENV: "  abc123 ", UID_ENV: " 456 "}):
            c = load_credentials()
        assert c.client_id == "abc123" and c.uid == "456"

    @case("punch_once 成功路径只请求一次")
    def _() -> None:
        calls: list = []
        r = punch_once(Credentials("abc", "1"), transport=fake_transport({"code": 200, "message": "ok"}, calls=calls))
        assert r.ok is True and r.code == 200
        assert r.extra["attempts"] == 1 and len(calls) == 1
        assert calls[0][0] == PUNCH_URL
        assert calls[0][1]["Cookie"] == "__client_id=abc; _uid=1;"

    @case("punch_once 网络异常后重试成功")
    def _() -> None:
        state = {"n": 0}

        def flaky(url: str, headers: dict[str, str], timeout: float) -> tuple[int, str]:
            state["n"] += 1
            if state["n"] < 3:
                raise OSError("connection reset")
            return 200, json.dumps({"code": 200, "message": "ok"})

        slept: list[float] = []
        r = punch_once(Credentials("abc", "1"), retries=3, transport=flaky, sleeper=slept.append)
        assert r.ok is True, r.message
        assert state["n"] == 3 and r.extra["attempts"] == 3
        assert len(slept) == 2 and slept[1] > slept[0], slept

    @case("punch_once 重试耗尽后返回失败")
    def _() -> None:
        def boom(url: str, headers: dict[str, str], timeout: float) -> tuple[int, str]:
            raise OSError("connection reset")

        r = punch_once(Credentials("abc", "1"), retries=2, transport=boom, sleeper=lambda _s: None)
        assert r.ok is False and r.extra["attempts"] == 2
        assert "connection reset" in r.message, r.message

    @case("punch_once 非法 JSON 返回失败")
    def _() -> None:
        def html(url: str, headers: dict[str, str], timeout: float) -> tuple[int, str]:
            return 200, "<html>404</html>"

        r = punch_once(Credentials("abc", "1"), retries=1, transport=html, sleeper=lambda _s: None)
        assert r.ok is False and "JSON" in r.message, r.message

    @case("punch_once 5xx 会重试")
    def _() -> None:
        calls: list = []

        def flaky(url: str, headers: dict[str, str], timeout: float) -> tuple[int, str]:
            calls.append(url)
            if len(calls) < 2:
                return 502, "bad gateway"
            return 200, json.dumps({"code": 200, "message": "ok"})

        r = punch_once(Credentials("abc", "1"), retries=3, transport=flaky, sleeper=lambda _s: None)
        assert r.ok is True and len(calls) == 2, (r.message, len(calls))

    @case("_parse_at 正常与非法")
    def _() -> None:
        assert _parse_at("10:00") == (10, 0)
        assert _parse_at("23:59") == (23, 59)
        for bad in ("25:00", "10:61", "abc", "10"):
            try:
                _parse_at(bad)
            except PunchError:
                pass
            else:
                raise AssertionError(f"{bad} 应当被拒")

    @case("_next_run 今天未到 / 已过")
    def _() -> None:
        tz = _shanghai_tz()
        now = datetime(2026, 11, 24, 9, 0, tzinfo=tz)
        assert _next_run(now, 10, 0).day == 24
        now2 = datetime(2026, 11, 24, 11, 0, tzinfo=tz)
        assert _next_run(now2, 10, 0).day == 25

    @case("定时模式按 max_runs 退出且只跑一次")
    def _() -> None:
        calls: list = []
        fake_result = PunchResult(True, 200, "打卡成功")
        runs = punch_with_schedule(
            Credentials("abc", "1"),
            at="10:00",
            max_runs=1,
            sleeper=lambda _s: None,
            runner=lambda: (calls.append(1), fake_result)[1],
            clock=lambda: datetime(2026, 11, 24, 9, 0, tzinfo=_shanghai_tz()),
        )
        assert runs == 1 and len(calls) == 1

    @case("时区回退链可用 (zoneinfo / pytz / 固定 UTC+8)")
    def _() -> None:
        tz = _shanghai_tz()
        offset = datetime(2026, 11, 24, 12, 0, tzinfo=tz).utcoffset()
        assert offset == timedelta(hours=8), offset

    passed = 0
    failed = 0
    print("洛谷打卡助手 离线自检")
    print("-" * 46)
    for name, fn in cases:
        try:
            fn()
        except AssertionError as exc:
            failed += 1
            print(f"  [FAIL] {name}: {exc}")
        except Exception as exc:
            failed += 1
            print(f"  [ERROR] {name}: {type(exc).__name__}: {exc}")
        else:
            passed += 1
            print(f"  [PASS] {name}")
    print("-" * 46)
    print(f"自检结果: {passed} passed / {failed} failed")
    return 0 if failed == 0 else 1


def main(argv: Optional[Iterable[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="洛谷每日打卡助手")
    ap.add_argument("--schedule", action="store_true", help="常驻, 每天定时打卡")
    ap.add_argument("--at", default=DEFAULT_AT, help="定时打卡时间 HH:MM (北京时间), 默认 10:00")
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="单次请求超时秒数, 默认 15")
    ap.add_argument("--retries", type=int, default=DEFAULT_RETRIES, help="失败重试次数, 默认 3")
    ap.add_argument("--max-runs", type=int, default=None, help="定时模式最多执行几次 (调试用)")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    ap.add_argument("--selftest", action="store_true", help="离线自检, 不联网")
    args = ap.parse_args(list(argv) if argv is not None else None)

    if args.selftest:
        return _selftest()

    try:
        if args.schedule:
            creds = load_credentials()
            punch_with_schedule(
                creds,
                at=args.at,
                timeout=args.timeout,
                retries=args.retries,
                max_runs=args.max_runs,
            )
            return 0
        result = run_once(timeout=args.timeout, retries=args.retries)
    except PunchError as exc:
        print(f"[配置错误] {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\n已中断", file=sys.stderr)
        return 130

    if args.json:
        print(json.dumps({
            "ok": result.ok,
            "code": result.code,
            "message": result.message,
            "elapsed_ms": result.elapsed_ms,
            "attempts": result.extra.get("attempts"),
            "http_status": result.extra.get("status"),
        }, ensure_ascii=False, indent=2))
    else:
        print(f"[{'成功' if result.ok else '失败'}] {result.message} "
              f"(code={result.code}, 用时 {result.elapsed_ms} ms, 尝试 {result.extra.get('attempts')} 次)")
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
