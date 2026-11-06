import copy
import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from _support import EXAMPLES, load_example
import render_report as rr


class TestRender(unittest.TestCase):
    def setUp(self):
        self.brief, self.arts = load_example()

    def test_sections_in_order(self):
        md = rr.render(self.brief, self.arts)
        heads = ["## 한눈에 보기", "## 1. 최신 사업 현황", "## 2. 주요 이슈", "## 3. 타임라인",
                 "## 4. 시사점", "## 5. 앞으로 지켜볼 것", "## 6. 한계와 확인하지 못한 것"]
        pos = [md.index(h) for h in heads]
        self.assertEqual(pos, sorted(pos))

    def test_unverified_figures_flagged(self):
        md = rr.render(self.brief, self.arts)
        i4 = md[md.index("### I4."):md.index("### I5.")]
        self.assertIn("수치 미확인", i4)
        i2 = md[md.index("### I2."):md.index("### I3.")]
        self.assertNotIn("수치 미확인", i2)

    def test_self_review_disclosed_and_no_internal_codes(self):
        md = rr.render(self.brief, self.arts)
        self.assertIn("자체 채점", md)
        self.assertNotIn("CONFIRMED", md.split("<details>")[0].replace("check_note", ""))

    def test_refuses_invalid_brief_without_force(self):
        b = copy.deepcopy(self.brief)
        b["issues"][0]["sources"] = ["A999"]
        with tempfile.TemporaryDirectory() as d:
            bp = Path(d) / "b.json"
            bp.write_text(__import__("json").dumps(b, ensure_ascii=False), encoding="utf-8")
            with redirect_stderr(io.StringIO()):
                self.assertEqual(rr.main([str(bp), str(EXAMPLES / "sample-articles.json")]), 1)
                out = Path(d) / "r.md"
                self.assertEqual(rr.main([str(bp), str(EXAMPLES / "sample-articles.json"), "--force", "--out", str(out)]), 0)
            self.assertIn("검사 미통과", out.read_text(encoding="utf-8"))

    def test_log_line_appended(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "newslearn-log.md"
            with redirect_stderr(io.StringIO()):
                rr.main([str(EXAMPLES / "sample-brief.json"), str(EXAMPLES / "sample-articles.json"),
                         "--out", str(Path(d) / "r.md"), "--log", str(log)])
            line = log.read_text(encoding="utf-8")
            self.assertIn("LG에너지솔루션", line)
            self.assertIn("I1 3차 ESS", line)

    def test_example_report_is_current(self):
        md = rr.render(self.brief, self.arts)
        self.assertEqual(md, (EXAMPLES / "sample-report.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
