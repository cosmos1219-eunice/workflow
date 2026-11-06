import copy
import unittest

from _support import load_example
import validate_brief as vb


class TestValidateBrief(unittest.TestCase):
    def setUp(self):
        self.brief, self.arts = load_example()

    def errs(self, brief):
        return vb.check(brief, self.arts)[0]

    def test_sample_passes(self):
        self.assertEqual(self.errs(self.brief), [])

    def test_hallucinated_source(self):
        b = copy.deepcopy(self.brief)
        b["issues"][0]["sources"].append("A999")
        self.assertTrue(any("A999" in e and "환각" in e for e in self.errs(b)))

    def test_high_signal_needs_two_publishers(self):
        b = copy.deepcopy(self.brief)
        b["issues"][6]["signal"] = "high"   # I7, 출처 3곳이지만 높여 보고 출처를 1개로 줄인다
        b["issues"][6]["sources"] = ["A143"]
        self.assertTrue(any("2곳 이상" in e for e in self.errs(b)))

    def test_rejected_issue_blocked(self):
        b = copy.deepcopy(self.brief)
        b["issues"][0]["check"] = "REJECTED"
        self.assertTrue(any("REJECTED" in e for e in self.errs(b)))

    def test_weakened_needs_note(self):
        b = copy.deepcopy(self.brief)
        b["issues"][2]["check_note"] = ""
        self.assertTrue(any("check_note" in e for e in self.errs(b)))

    def test_implication_must_have_next_action_and_real_issue(self):
        b = copy.deepcopy(self.brief)
        b["implications"][0]["next_action"] = ""
        b["implications"][1]["issues"] = ["I99"]
        e = self.errs(b)
        self.assertTrue(any("next_action" in x for x in e))
        self.assertTrue(any("I99" in x for x in e))

    def test_so_what_cannot_repeat_title(self):
        b = copy.deepcopy(self.brief)
        b["implications"][0]["so_what"] = b["implications"][0]["title"]
        self.assertTrue(any("반복" in e for e in self.errs(b)))

    def test_timeline_order_and_window(self):
        b = copy.deepcopy(self.brief)
        b["timeline"][0]["date"] = "2026-12-31"
        self.assertTrue(any("밖" in e for e in self.errs(b)))
        b = copy.deepcopy(self.brief)
        b["timeline"][0], b["timeline"][1] = b["timeline"][1], b["timeline"][0]
        self.assertTrue(any("오름차순" in e for e in self.errs(b)))

    def test_review_gate(self):
        b = copy.deepcopy(self.brief)
        b["review"]["scores"]["so_what"] = 6
        self.assertTrue(any("so_what=6" in e for e in self.errs(b)))
        b = copy.deepcopy(self.brief)
        del b["review"]
        self.assertTrue(any("review.scores" in e for e in self.errs(b)))

    def test_counts(self):
        b = copy.deepcopy(self.brief)
        b["summary"] = b["summary"][:2]
        self.assertTrue(any("'summary'" in e for e in self.errs(b)))

    def test_sparse_mode_relaxes_minimums(self):
        b = copy.deepcopy(self.brief)
        arts = copy.deepcopy(self.arts)
        keep = {s for sec in ("status", "issues", "timeline") for x in b[sec][:2] for s in x["sources"]}
        b["issues"] = b["issues"][:1]
        b["implications"] = [dict(b["implications"][0], issues=["I1"]), dict(b["implications"][1], issues=["I1"])]
        b["status"], b["timeline"], b["watchlist"] = b["status"][:2], b["timeline"][:2], b["watchlist"][:2]
        b["summary"] = b["summary"][:2]
        keep |= {s for x in b["issues"] for s in x["sources"]}
        arts["articles"] = [a for a in arts["articles"] if a["id"] in keep][:29]
        b["status"] = [s for s in b["status"] if all(i in keep for i in s["sources"])] or b["status"]
        errors, _, stats = vb.check(b, arts)
        self.assertTrue(stats["sparse_mode"])
        self.assertFalse(any("개여야 함" in e for e in errors), errors)

    def test_figure_warning(self):
        _, warnings, _ = vb.check(self.brief, self.arts)
        self.assertTrue(any("I4" in w and "수치" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()
