import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import check_inputs as c  # noqa: E402


def target(ra=10.0, dec=0.0, tmag=11.0):
    return {"tic": "1", "ra_deg": str(ra), "dec_deg": str(dec), "tmag": str(tmag)}


def record(ra=10.0, dec=0.0, tmag=11.0):
    return {"ra": str(ra), "dec": str(dec), "tmag": str(tmag)}


class CompareTests(unittest.TestCase):
    def test_exact_match_has_no_problem(self):
        sep, dm, problems = c.compare_one(target(), record())
        self.assertEqual(problems, [])
        self.assertAlmostEqual(sep, 0.0)

    def test_rounding_sized_offset_is_accepted(self):
        # 0.0004 degree in each coordinate is inside the rounding of 0.001 degree
        sep, dm, problems = c.compare_one(target(), record(ra=10.0004, dec=0.0004))
        self.assertEqual(problems, [])
        self.assertGreater(sep, 1.0)

    def test_big_position_offset_is_flagged(self):
        _, _, problems = c.compare_one(target(), record(ra=10.002, dec=0.0))
        self.assertEqual(len(problems), 1)
        self.assertIn("position", problems[0])

    def test_tmag_offset_is_flagged(self):
        _, _, problems = c.compare_one(target(tmag=11.00), record(tmag=11.02))
        self.assertEqual(len(problems), 1)
        self.assertIn("Tmag", problems[0])

    def test_missing_record(self):
        self.assertEqual(c.compare_one(target(), None), (None, None, ["not in TIC"]))

    def test_east_west_limit_shrinks_with_declination(self):
        self.assertLess(c.position_limit_arcsec(80.0), c.position_limit_arcsec(0.0))

    def test_committed_run_flags_nothing(self):
        out = c.run(os.path.join(ROOT, "targets_eumemic.csv"), os.path.join(ROOT, "snapshots"))
        self.assertEqual(out["candidate_rows"], 665)
        self.assertEqual(out["distinct_tic_ids"], 651)
        self.assertEqual(out["flagged"], [])


if __name__ == "__main__":
    unittest.main()
