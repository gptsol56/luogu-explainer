# -*- coding: utf-8 -*-
"""luogu_punch 的单元测试。

零外部依赖 (只用标准库 unittest), 所以 CI 与本地都能直接跑:
    python -m unittest discover -s tests -v
"""
import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import luogu_punch as lp


class TestInterpret(unittest.TestCase):
    """返回码解释: code 必须与 message 一起判定。"""

    def test_code_200_success(self):
        ok, msg = lp.interpret({"code": 200, "message": "打卡成功"})
        self.assertTrue(ok)
        self.assertEqual(msg, "打卡成功")

    def test_code_201_not_logged_in(self):
        ok, msg = lp.interpret({"code": 201, "message": "请登录洛谷进行打卡，获得今日运势。"})
        self.assertFalse(ok, "未登录必须判为失败, 不能当成已打卡")
        self.assertIn("请登录", msg)

    def test_code_201_already_punched(self):
        ok, _ = lp.interpret({"code": 201, "message": "今天已经打过卡啦"})
        self.assertTrue(ok)

    def test_code_201_without_message(self):
        ok, msg = lp.interpret({"code": 201})
        self.assertTrue(ok)
        self.assertIn("已打卡", msg)

    def test_auth_errors(self):
        self.assertFalse(lp.interpret({"code": 401})[0])
        self.assertFalse(lp.interpret({"code": 403})[0])

    def test_rate_limited(self):
        ok, msg = lp.interpret({"code": 429})
        self.assertFalse(ok)
        self.assertIn("频繁", msg)

    def test_unknown_code(self):
        ok, msg = lp.interpret({"code": 777})
        self.assertFalse(ok)
        self.assertIn("777", msg)

    def test_missing_code_field(self):
        ok, _ = lp.interpret({})
        self.assertFalse(ok)


class TestCredentials(unittest.TestCase):

    def _env(self, **kwargs):
        saved = {k: os.environ.get(k) for k in kwargs}
        for key, value in kwargs.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.addCleanup(self._restore, saved)

    @staticmethod
    def _restore(saved):
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_cookie_format(self):
        self.assertEqual(lp.Credentials("abc", "1").cookie, "__client_id=abc; _uid=1;")

    def test_headers(self):
        headers = lp.build_headers(lp.Credentials("abc", "1"))
        self.assertEqual(set(headers), {"Cookie", "User-Agent", "Referer"})
        self.assertEqual(headers["Cookie"], "__client_id=abc; _uid=1;")

    def test_missing_credentials(self):
        self._env(**{lp.CLIENT_ID_ENV: None, lp.UID_ENV: None})
        with self.assertRaises(lp.PunchError) as ctx:
            lp.load_credentials()
        self.assertIn(lp.CLIENT_ID_ENV, str(ctx.exception))
        self.assertIn(lp.UID_ENV, str(ctx.exception))

    def test_bad_client_id(self):
        self._env(**{lp.CLIENT_ID_ENV: "abc-123", lp.UID_ENV: "1"})
        with self.assertRaises(lp.PunchError):
            lp.load_credentials()

    def test_bad_uid(self):
        self._env(**{lp.CLIENT_ID_ENV: "abc", lp.UID_ENV: "12a"})
        with self.assertRaises(lp.PunchError):
            lp.load_credentials()

    def test_strips_whitespace(self):
        self._env(**{lp.CLIENT_ID_ENV: "  abc  ", lp.UID_ENV: " 12 "})
        creds = lp.load_credentials()
        self.assertEqual(creds.client_id, "abc")
        self.assertEqual(creds.uid, "12")


class TestPunchOnce(unittest.TestCase):

    @staticmethod
    def _transport(payload, status=200, calls=None):
        def _t(url, headers, timeout):
            if calls is not None:
                calls.append((url, headers, timeout))
            return status, lp.json.dumps(payload, ensure_ascii=False)
        return _t

    def test_success_single_attempt(self):
        calls = []
        result = lp.punch_once(lp.Credentials("abc", "1"),
                               transport=self._transport({"code": 200, "message": "ok"}, calls=calls))
        self.assertTrue(result.ok)
        self.assertEqual(result.code, 200)
        self.assertEqual(result.extra["attempts"], 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], lp.PUNCH_URL)

    def test_retries_then_succeeds(self):
        state = {"n": 0}

        def flaky(url, headers, timeout):
            state["n"] += 1
            if state["n"] < 3:
                raise OSError("connection reset")
            return 200, '{"code": 200, "message": "ok"}'

        slept = []
        result = lp.punch_once(lp.Credentials("abc", "1"), retries=3, transport=flaky, sleeper=slept.append)
        self.assertTrue(result.ok)
        self.assertEqual(state["n"], 3)
        self.assertEqual(result.extra["attempts"], 3)
        self.assertEqual(len(slept), 2)
        self.assertGreater(slept[1], slept[0], "退避间隔必须递增")

    def test_retry_exhausted(self):
        def boom(url, headers, timeout):
            raise OSError("connection reset")

        result = lp.punch_once(lp.Credentials("abc", "1"), retries=2, transport=boom, sleeper=lambda _s: None)
        self.assertFalse(result.ok)
        self.assertEqual(result.extra["attempts"], 2)
        self.assertIn("connection reset", result.message)

    def test_invalid_json(self):
        def html(url, headers, timeout):
            return 200, "<html>404</html>"

        result = lp.punch_once(lp.Credentials("abc", "1"), retries=1, transport=html, sleeper=lambda _s: None)
        self.assertFalse(result.ok)
        self.assertIn("JSON", result.message)

    def test_5xx_is_retried(self):
        calls = []

        def flaky(url, headers, timeout):
            calls.append(url)
            if len(calls) < 2:
                return 502, "bad gateway"
            return 200, '{"code": 200, "message": "ok"}'

        result = lp.punch_once(lp.Credentials("abc", "1"), retries=3, transport=flaky, sleeper=lambda _s: None)
        self.assertTrue(result.ok)
        self.assertEqual(len(calls), 2)


class TestSchedule(unittest.TestCase):

    def test_parse_at(self):
        self.assertEqual(lp._parse_at("10:00"), (10, 0))
        self.assertEqual(lp._parse_at("23:59"), (23, 59))
        for bad in ("25:00", "10:61", "abc", "10"):
            with self.assertRaises(lp.PunchError):
                lp._parse_at(bad)

    def test_next_run_today_and_tomorrow(self):
        tz = lp._shanghai_tz()
        now = datetime(2026, 11, 24, 9, 0, tzinfo=tz)
        self.assertEqual(lp._next_run(now, 10, 0).day, 24)
        later = datetime(2026, 11, 24, 11, 0, tzinfo=tz)
        self.assertEqual(lp._next_run(later, 10, 0).day, 25)

    def test_schedule_stops_after_max_runs(self):
        calls = []
        fake = lp.PunchResult(True, 200, "打卡成功")
        runs = lp.punch_with_schedule(
            lp.Credentials("abc", "1"), at="10:00", max_runs=1,
            sleeper=lambda _s: None,
            runner=lambda: (calls.append(1), fake)[1],
            clock=lambda: datetime(2026, 11, 24, 9, 0, tzinfo=lp._shanghai_tz()),
        )
        self.assertEqual(runs, 1)
        self.assertEqual(len(calls), 1)


class TestTimezone(unittest.TestCase):

    def test_shanghai_offset_is_utc8(self):
        tz = lp._shanghai_tz()
        offset = datetime(2026, 11, 24, 12, 0, tzinfo=tz).utcoffset()
        self.assertEqual(offset, timedelta(hours=8))


if __name__ == "__main__":
    unittest.main(verbosity=2)