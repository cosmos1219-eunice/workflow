import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from datetime import date
from pathlib import Path

from _support import FIXTURES
import fetch_news as fn


class TestQuery(unittest.TestCase):
    def test_single_keyword_quoted(self):
        self.assertEqual(fn.build_query("가나전자"), '"가나전자"')

    def test_alias_exclude_dates(self):
        q = fn.build_query("가나전자", ["가나"], ["채용"], date(2026, 8, 1), date(2026, 8, 15))
        self.assertEqual(q, '("가나전자" OR "가나") -"채용" after:2026-08-01 before:2026-08-15')

    def test_ascii_keyword_not_quoted(self):
        self.assertEqual(fn.build_query("Tesla"), "Tesla")

    def test_windows_cover_range_without_gaps(self):
        ws = fn.split_windows(date(2026, 8, 9), date(2026, 11, 6), 6)
        self.assertEqual(ws[0][0], date(2026, 8, 9))
        self.assertEqual(ws[-1][1], date(2026, 11, 6))
        for (a0, a1), (b0, _) in zip(ws, ws[1:]):
            self.assertEqual((b0 - a1).days, 1)


class TestParseAndDedupe(unittest.TestCase):
    def setUp(self):
        self.items = fn.parse_feed((FIXTURES / "sample_feed.xml").read_text(encoding="utf-8"), "ko")

    def test_parse_strips_source_suffix_and_skips_bad_dates(self):
        titles = [i["title"] for i in self.items]
        self.assertIn("가나전자, 미국 공장 착공", titles)  # 언론사 이름이 두 번 붙은 경우
        self.assertEqual(len(self.items), 7)  # 날짜가 잘못된 1건 제외

    def test_near_duplicates_merged_with_other_sources(self):
        merged = fn.dedupe(self.items)
        top = [m for m in merged if "영업이익" in m["title"]]
        self.assertEqual(len(top), 1)
        self.assertEqual(top[0]["dup_count"], 3)
        self.assertEqual(top[0]["source"], "한빛일보")  # 가장 먼저 보도한 곳이 대표
        self.assertEqual(sorted(top[0]["also_in"]), ["다온경제", "새벽신문"])

    def test_different_events_not_merged(self):
        merged = fn.dedupe(self.items)
        self.assertGreaterEqual(len(merged), 5)


class TestBalance(unittest.TestCase):
    def test_balance_keeps_every_week(self):
        from datetime import datetime, timedelta, timezone
        base = datetime(2026, 8, 3, tzinfo=timezone.utc)
        items = []
        for d in range(0, 28):  # 4주, 마지막 주에 기사가 몰림
            n = 20 if d >= 21 else 2
            for k in range(n):
                items.append({"published": base + timedelta(days=d), "dup_count": 1, "title": f"{d}-{k}"})
        kept, dropped = fn.balance(items, 40)
        self.assertEqual(len(kept), 40)
        self.assertEqual(dropped, len(items) - 40)
        weeks = {a["published"].isocalendar()[1] for a in kept}
        self.assertEqual(len(weeks), 4)

    def test_no_cap(self):
        kept, dropped = fn.balance([{"published": None}] * 3, 0)
        self.assertEqual((len(kept), dropped), (3, 0))


class TestMainWithFixture(unittest.TestCase):
    def test_end_to_end_fixture(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "articles.json"
            with redirect_stderr(io.StringIO()):
                code = fn.main(["가나전자", "--exclude", "채용", "--fixture", str(FIXTURES / "sample_feed.xml"),
                                "--today", "2026-11-06", "--out", str(out)])
            self.assertEqual(code, 0)
            data = json.loads(out.read_text(encoding="utf-8"))
            titles = [a["title"] for a in data["articles"]]
            self.assertFalse(any("채용" in t for t in titles))       # 제외어
            self.assertFalse(any("작년 일" in t for t in titles))    # 90일 밖
            self.assertEqual(data["articles"][0]["id"], "A001")
            self.assertGreaterEqual(data["articles"][0]["published"], data["articles"][-1]["published"])
            self.assertTrue(out.with_suffix(".txt").exists())
            self.assertIn("(x3)", out.with_suffix(".txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
