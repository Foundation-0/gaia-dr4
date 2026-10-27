import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import simbad_check as sc  # noqa: E402
from ticmap import read_csv_dicts  # noqa: E402


def found(tic=None, dr2=None, dr3=None):
    return {"tic": tic, "dr2": dr2, "dr3": dr3}


class VerdictTests(unittest.TestCase):
    def test_every_combination_of_names_found_on_one_object(self):
        self.assertEqual(sc.verdict_for(found(7, 7, 7)), "agree_all_three")
        self.assertEqual(sc.verdict_for(found(7, None, 7)), "agree_tic_dr3_only")
        self.assertEqual(sc.verdict_for(found(None, 7, 7)), "agree_dr2_dr3_only")
        self.assertEqual(sc.verdict_for(found(7, 7, None)), "agree_tic_dr2_only")
        self.assertEqual(sc.verdict_for(found(None, None, 7)), "one_name_only")
        self.assertEqual(sc.verdict_for(found(7, None, None)), "one_name_only")
        self.assertEqual(sc.verdict_for(found()), "not_in_simbad")

    def test_names_on_different_objects_disagree(self):
        self.assertEqual(sc.verdict_for(found(7, 7, 8)), "disagree")
        self.assertEqual(sc.verdict_for(found(7, None, 8)), "disagree")
        self.assertEqual(sc.verdict_for(found(None, 6, 8)), "disagree")


class SpotCheckTests(unittest.TestCase):
    def rows(self, n_ambiguous=13, n_plain=100):
        rows = [{"tic": str(1000 + i), "status": "ambiguous"} for i in range(n_ambiguous)]
        rows += [{"tic": str(5000 + i), "status": "one-to-one"} for i in range(n_plain)]
        return rows

    def test_ten_targets_four_ambiguous_and_the_same_every_time(self):
        a = sc.choose_spot_checks(self.rows())
        self.assertEqual(len(a), 10)
        self.assertEqual(sum(1 for t in a if int(t) < 5000), 4)
        self.assertEqual(a, sc.choose_spot_checks(list(reversed(self.rows()))))

    def test_the_draw_does_not_look_at_what_simbad_said(self):
        rows = self.rows()
        for r in rows:
            r["verdict"] = "not_in_simbad"
        self.assertEqual(sc.choose_spot_checks(rows), sc.choose_spot_checks(self.rows()))

    def test_few_ambiguous_targets_are_all_taken_and_the_rest_filled_up(self):
        a = sc.choose_spot_checks(self.rows(n_ambiguous=2, n_plain=50))
        self.assertEqual(len(a), 10)
        self.assertEqual(sum(1 for t in a if int(t) < 5000), 2)

    def test_small_lists_give_fewer_than_ten(self):
        self.assertEqual(len(sc.choose_spot_checks(self.rows(n_ambiguous=1, n_plain=3))), 4)


class CommittedResultTests(unittest.TestCase):
    def setUp(self):
        self.csv_path = os.path.join(ROOT, "snapshots", "simbad_crosscheck.csv")
        self.table = os.path.join(ROOT, "tic_to_gaia_dr3.csv")
        if not (os.path.exists(self.csv_path) and os.path.exists(self.table)):
            self.skipTest("committed files not present")

    def test_marked_spot_checks_are_the_ones_the_code_draws(self):
        table = read_csv_dicts(self.table)
        drawn = sc.choose_spot_checks(table)
        marked = {r["tic"] for r in read_csv_dicts(self.csv_path) if r["spot_check"] == "yes"}
        self.assertEqual(marked, drawn)

    def test_no_disagreement_and_the_counts_add_up(self):
        rows = read_csv_dicts(self.csv_path)
        counts = {}
        for r in rows:
            counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
        self.assertEqual(len(rows), 651)
        self.assertNotIn("disagree", counts)
        # the verdict agrees with the three yes/no columns of the same row
        for r in rows:
            names = {k for k, c in (("tic", "found_tic_name"), ("dr2", "found_dr2_name"),
                                    ("dr3", "found_dr3_name")) if r[c] == "yes"}
            if r["verdict"] == "agree_all_three":
                self.assertEqual(names, {"tic", "dr2", "dr3"})
            elif r["verdict"] == "agree_tic_dr3_only":
                self.assertEqual(names, {"tic", "dr3"})
            elif r["verdict"] == "not_in_simbad":
                self.assertEqual(names, set())


if __name__ == "__main__":
    unittest.main()
