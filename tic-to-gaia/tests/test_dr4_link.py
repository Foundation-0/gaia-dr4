import csv
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "release_day"))

import dr4_link as d  # noqa: E402


class NeighbourhoodRouteTests(unittest.TestCase):
    """Route 1 is tested on made-up rows only: the real table does not exist yet."""

    def test_query_text(self):
        q = d.neighbourhood_query([11, 22])
        self.assertIn("gaiadr4.dr3_neighbourhood", q)
        self.assertIn("dr3_source_id IN (11,22)", q)
        self.assertIn("source_id AS dr4_source_id", q)
        self.assertIn("probable_match", q)

    def test_query_refuses_non_numbers(self):
        with self.assertRaises(ValueError):
            d.neighbourhood_query(["1) OR (1=1"])

    def test_probable_rule_edges(self):
        self.assertTrue(d.is_probable(59.9, -0.25))
        self.assertTrue(d.is_probable(0.0, 0.35))
        self.assertFalse(d.is_probable(60.0, 0.0))
        self.assertFalse(d.is_probable(10.0, 0.36))
        self.assertFalse(d.is_probable(10.0, -0.26))
        self.assertFalse(d.is_probable(10.0, None))

    def test_choose(self):
        c = lambda dr4, dist, dmag, p=None: {"dr4": dr4, "dist": dist, "dmag": dmag, "probable": p}
        self.assertEqual(d.choose_from_neighbourhood([]), (None, "no match"))
        best, status = d.choose_from_neighbourhood([c(5, 1.0, 0.0)])
        self.assertEqual((best["dr4"], status), (5, "one-to-one"))
        # closest is not photometrically consistent: take the next one, and say ambiguous
        best, status = d.choose_from_neighbourhood([c(5, 1.0, 2.0), c(6, 30.0, 0.0)])
        self.assertEqual((best["dr4"], status), (6, "ambiguous"))
        # the table's own probable_match column wins over our recomputation
        best, status = d.choose_from_neighbourhood([c(5, 1.0, 0.0, False), c(6, 30.0, 0.0, True)])
        self.assertEqual(best["dr4"], 6)
        self.assertEqual(d.choose_from_neighbourhood([c(5, 100.0, 0.0)]), (None, "no match"))


class PositionRouteTests(unittest.TestCase):
    def test_expected_position_uses_proper_motion(self):
        ra, dec = d.expected_position({"ra": 10.0, "dec": 0.0, "pmra": 0.0, "pmdec": 100.0},
                                      2016.0, 2017.5)
        self.assertAlmostEqual((dec - 0.0) * 3600, 0.15, places=9)

    def test_cone_query_shape(self):
        q = d.cone_query([(10.0, 20.0), (11.0, -5.0)], "gaiadr4.gaia_source", 2.0)
        self.assertTrue(q.startswith("SELECT source_id, ra, dec"))
        self.assertIn("FROM gaiadr4.gaia_source WHERE", q)
        self.assertEqual(q.count("CONTAINS"), 2)
        self.assertEqual(q.count(" OR "), 1)
        self.assertIn("CIRCLE('ICRS', 10.000000000, 20.000000000, 0.000555556)", q)
        with self.assertRaises(ValueError):
            d.cone_query([], "gaiadr4.gaia_source")

    def test_cone_query_all_sources_joins_the_two_complete_tables(self):
        q = d.cone_query_all_sources([(10.0, 20.0), (11.0, -5.0)], 2.0)
        self.assertIn("FROM gaiadr4.all_source_astrometry AS a LEFT JOIN "
                      "gaiadr4.all_source_photometry AS p ON p.source_id = a.source_id", q)
        self.assertIn("p.phot_g_mean_mag AS phot_g_mean_mag", q)
        self.assertIn("a.ref_epoch AS ref_epoch", q)
        self.assertEqual(q.count("CONTAINS(POINT('ICRS', a.ra, a.dec)"), 2)
        self.assertEqual(q.count(" OR "), 1)
        with self.assertRaises(ValueError):
            d.cone_query_all_sources([])

    def test_both_cone_queries_return_the_columns_parse_cone_answer_reads(self):
        for q in (d.cone_query([(1.0, 2.0)], "gaiadr4.gaia_source"),
                  d.cone_query_all_sources([(1.0, 2.0)])):
            for column in ("source_id", "ra", "dec", "phot_g_mean_mag", "ref_epoch"):
                self.assertIn(column, q)

    def cand(self, sid, dra_arcsec, g=12.0):
        return {"source_id": sid, "ra": 10.0 + dra_arcsec / 3600.0, "dec": 0.0, "g": g}

    def test_match_by_position(self):
        exp = {"ra": 10.0, "dec": 0.0, "g": 12.0}
        best, status, n = d.match_by_position(exp, [self.cand(1, 0.01), self.cand(2, 30.0)])
        self.assertEqual((best["source_id"], status, n), (1, "one-to-one", 1))
        best, status, n = d.match_by_position(exp, [self.cand(1, 0.01), self.cand(2, 1.5, 15.0)])
        self.assertEqual((best["source_id"], status, n), (1, "ambiguous", 2))
        self.assertEqual(d.match_by_position(exp, [self.cand(2, 30.0)]), (None, "no match", 0))

    def test_magnitude_window_removes_inconsistent_source(self):
        exp = {"ra": 10.0, "dec": 0.0, "g": 12.0}
        best, status, n = d.match_by_position(exp, [self.cand(1, 0.01, 14.0), self.cand(2, 0.5, 12.1)])
        self.assertEqual(best["source_id"], 2)
        self.assertEqual(n, 2)
        self.assertEqual(d.match_by_position(exp, [self.cand(1, 0.01, 14.0)]), (None, "no match", 1))

    def test_unknown_magnitude_skips_the_window(self):
        exp = {"ra": 10.0, "dec": 0.0, "g": None}
        best, _, _ = d.match_by_position(exp, [self.cand(1, 0.01, 20.0)])
        self.assertEqual(best["source_id"], 1)

    def test_parse_cone_answer(self):
        names = ["source_id", "ra", "dec", "pmra", "pmdec", "phot_g_mean_mag", "ruwe", "ref_epoch"]
        rows = [["5", "10.5", "-3.25", "", "", "", "1.0", "2017.5"]]
        self.assertEqual(d.parse_cone_answer(names, rows),
                         [{"source_id": 5, "ra": 10.5, "dec": -3.25, "g": None, "ref_epoch": 2017.5}])
        # an answer without the column still parses; the epoch is then unknown
        got = d.parse_cone_answer(["source_id", "ra", "dec", "phot_g_mean_mag"], [["5", "1", "2", "13"]])
        self.assertIsNone(got[0]["ref_epoch"])


class TargetPositionTests(unittest.TestCase):
    """Expected J2017.5 positions, on small made-up files."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def write(self, name, header, rows):
        with open(os.path.join(self.tmp, name), "w", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(header)
            w.writerows(rows)

    def test_missing_dr3_proper_motion_falls_back_to_the_tic(self):
        self.write("table.csv", ["tic", "dr3_source_id", "status"],
                   [["1", "100", "one-to-one"], ["2", "200", "one-to-one"]])
        self.write("dr3_gaia_source.csv", ["source_id", "ref_epoch", "ra", "dec", "pmra", "pmdec",
                                           "phot_g_mean_mag"],
                   [["100", "2016.0", "10", "0", "0", "100", "12"],
                    ["200", "2016.0", "20", "0", "", "", "13"]])
        self.write("tic_records.csv", ["tic", "pmra", "pmdec"],
                   [["1", "5", "5"], ["2", "0", "200"]])
        got = {t["tic"]: t for t in d.target_positions(
            os.path.join(self.tmp, "table.csv"), self.tmp, 2017.5)}
        self.assertEqual(got["1"]["pm_from"], "dr3")
        self.assertAlmostEqual(got["1"]["dec"] * 3600, 0.15, places=9)   # 100 mas/yr * 1.5 yr
        self.assertEqual(got["2"]["pm_from"], "tic")
        self.assertAlmostEqual(got["2"]["dec"] * 3600, 0.30, places=9)   # 200 mas/yr * 1.5 yr

    def test_no_proper_motion_anywhere_leaves_the_position(self):
        self.write("table.csv", ["tic", "dr3_source_id", "status"], [["3", "300", "ambiguous"]])
        self.write("dr3_gaia_source.csv", ["source_id", "ref_epoch", "ra", "dec", "pmra", "pmdec",
                                           "phot_g_mean_mag"], [["300", "2016.0", "30", "5", "", "", ""]])
        self.write("tic_records.csv", ["tic", "pmra", "pmdec"], [["3", "", ""]])
        (t,) = d.target_positions(os.path.join(self.tmp, "table.csv"), self.tmp, 2017.5)
        self.assertEqual((t["pm_from"], t["ra"], t["dec"], t["g"]), ("none", 30.0, 5.0, None))


class MatchNeighbourhoodTests(unittest.TestCase):
    """Route 1 on made-up answer files (the real table does not exist yet)."""

    HEADER = "dr3_source_id,dr4_source_id,angular_distance,magnitude_difference," \
             "proper_motion_propagation,probable_match\n"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def answer(self, name, lines, header=None):
        with open(os.path.join(self.tmp, name), "w") as fh:
            fh.write(self.HEADER if header is None else header)
            fh.write("".join(l + "\n" for l in lines))

    def test_one_clear_match_and_one_ambiguous_and_one_missing(self):
        self.answer("answer_000.csv", [
            "10,10,0.5,0.01,true,true",                 # clear
            "20,20,0.5,0.01,true,true",                 # two neighbours, one probable
            "20,21,1500.0,4.0,true,false",
            "30,31,900.0,3.0,true,false",               # only an improbable neighbour
        ])
        by = d.read_neighbourhood_answers(self.tmp)
        rows = {r[0]: r for r in d.match_neighbourhood([("1", 10), ("2", 20), ("3", 30), ("4", 40)], by)}
        self.assertEqual(rows["1"][2:4], [10, "one-to-one"])
        self.assertEqual(rows["1"][11], "no")
        self.assertEqual(rows["2"][2:4], [20, "ambiguous"])
        self.assertEqual(rows["2"][5], 1)                        # one probable match
        self.assertEqual(rows["3"][3], "no match")
        self.assertEqual(rows["3"][11], "yes")
        self.assertEqual(rows["4"][3], "no match")
        self.assertIn("absent", rows["4"][12])

    def test_two_targets_choosing_the_same_dr4_source_are_ambiguous(self):
        self.answer("answer_000.csv", ["10,99,0.5,0.0,true,true", "11,99,0.7,0.0,true,true"])
        by = d.read_neighbourhood_answers(self.tmp)
        rows = d.match_neighbourhood([("1", 10), ("2", 11)], by)
        self.assertEqual([r[3] for r in rows], ["ambiguous", "ambiguous"])
        self.assertEqual([r[10] for r in rows], [2, 2])
        self.assertEqual(rows[0][9], "no")

    def test_probable_match_is_recomputed_when_the_column_is_missing(self):
        self.answer("answer_000.csv", ["10,10,5.0,0.0,true", "11,11,500.0,0.0,true"],
                    header="dr3_source_id,dr4_source_id,angular_distance,magnitude_difference,"
                           "proper_motion_propagation\n")
        by = d.read_neighbourhood_answers(self.tmp)
        rows = d.match_neighbourhood([("1", 10), ("2", 11)], by)
        self.assertEqual([r[3] for r in rows], ["one-to-one", "no match"])
        self.assertEqual(rows[0][8], "computed")

    def test_missing_column_stops_everything(self):
        self.answer("answer_000.csv", ["1,1,0.1,0.0"], header="dr3_source_id,dr4_source_id,"
                    "angular_distance,magnitude_difference\n")
        with self.assertRaises(ValueError) as ctx:
            d.read_neighbourhood_answers(self.tmp)
        self.assertIn("proper_motion_propagation", str(ctx.exception))

    def test_no_answer_files_is_an_error(self):
        with self.assertRaises(ValueError):
            d.read_neighbourhood_answers(self.tmp)

    def test_parse_bool(self):
        self.assertEqual([d.parse_bool(x) for x in ("true", "False", "t", "f", "1", "0", "", "x")],
                         [True, False, True, False, True, False, None, None])


class EveryQueryHasAnAnswerTests(unittest.TestCase):
    """A batch with no answer must stop the match commands, not look like 'no match'."""

    HEADER = "source_id,ra,dec,pmra,pmdec,phot_g_mean_mag,ruwe,ref_epoch\n"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def touch(self, name, text=""):
        with open(os.path.join(self.tmp, name), "w") as fh:
            fh.write(text)

    def test_missing_answer_is_named(self):
        for n in ("000", "001", "002"):
            self.touch("position_batch_%s.adql" % n, "-- query\n")
        self.touch("answer_000.csv", self.HEADER)
        with self.assertRaises(ValueError) as ctx:
            d.check_every_query_has_an_answer(self.tmp, d.POSITION_PREFIX)
        self.assertIn("answer_001.csv", str(ctx.exception))
        self.assertIn("answer_002.csv", str(ctx.exception))
        self.assertNotIn("answer_000.csv,", str(ctx.exception))

    def test_complete_set_passes_and_is_counted(self):
        for n in ("000", "001"):
            self.touch("dr3_to_dr4_batch_%s.adql" % n)
            self.touch("answer_%s.csv" % n, "x\n")
        self.assertEqual(d.check_every_query_has_an_answer(self.tmp, d.NEIGHBOURHOOD_PREFIX), 2)

    def test_the_two_routes_do_not_mix_up_their_query_files(self):
        self.touch("position_batch_000.adql")
        self.assertEqual(d.check_every_query_has_an_answer(self.tmp, d.NEIGHBOURHOOD_PREFIX), 0)

    def test_match_positions_stops_when_an_answer_is_missing(self):
        self.touch("position_batch_000.adql")
        self.touch("position_batch_001.adql")
        self.touch("expected_positions.csv",
                   "tic,dr3_source_id,ra_j2017_5,dec_j2017_5,dr3_g,pm_from\n1,10,10.0,0.0,12.0,dr3\n")
        self.touch("answer_000.csv", self.HEADER)
        with self.assertRaises(ValueError):
            d.main(["match-positions", "--dir", self.tmp, "--out", os.path.join(self.tmp, "o.csv")])

    def test_match_neighbourhood_stops_when_an_answer_is_missing(self):
        table = os.path.join(ROOT, "tic_to_gaia_dr3.csv")
        if not os.path.exists(table):
            self.skipTest("table not present")
        self.touch("dr3_to_dr4_batch_000.adql")
        with self.assertRaises(ValueError):
            d.main(["match-neighbourhood", "--dir", self.tmp, "--out", os.path.join(self.tmp, "o.csv")])

    def test_match_positions_reports_the_reference_epoch(self):
        self.touch("position_batch_000.adql")
        self.touch("expected_positions.csv",
                   "tic,dr3_source_id,ra_j2017_5,dec_j2017_5,dr3_g,pm_from\n"
                   "1,10,10.0,0.0,12.0,dr3\n2,20,20.0,0.0,12.0,dr3\n")
        self.touch("answer_000.csv", self.HEADER +
                   "100,10.0,0.0,1,1,12.0,1.0,2017.5\n200,20.0,0.0,1,1,12.0,1.0,2016.0\n")
        out = os.path.join(self.tmp, "o.csv")
        d.main(["match-positions", "--dir", self.tmp, "--out", out])
        with open(out) as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual([r["ref_epoch"] for r in rows], ["2017.5", "2016"])

    def test_empty_answer_file_is_an_error(self):
        self.touch("expected_positions.csv",
                   "tic,dr3_source_id,ra_j2017_5,dec_j2017_5,dr3_g,pm_from\n1,10,10.0,0.0,12.0,dr3\n")
        self.touch("answer_000.csv", "")
        with self.assertRaises(ValueError):
            d.main(["match-positions", "--dir", self.tmp, "--out", os.path.join(self.tmp, "o.csv")])


class CompareRoutesTests(unittest.TestCase):
    def test_every_verdict(self):
        n = [{"tic": "1", "dr3_source_id": "10", "dr4_source_id": "100"},
             {"tic": "2", "dr3_source_id": "20", "dr4_source_id": "200"},
             {"tic": "3", "dr3_source_id": "30", "dr4_source_id": "300"},
             {"tic": "4", "dr3_source_id": "40", "dr4_source_id": ""}]
        p = [{"tic": "1", "dr3_source_id": "10", "dr4_source_id_by_position": "100"},
             {"tic": "2", "dr3_source_id": "20", "dr4_source_id_by_position": "201"},
             {"tic": "4", "dr3_source_id": "40", "dr4_source_id_by_position": ""},
             {"tic": "5", "dr3_source_id": "50", "dr4_source_id_by_position": "500"}]
        got = {r[0]: r[4] for r in d.compare_routes(n, p)}
        self.assertEqual(got, {"1": "agree", "2": "disagree", "3": "only neighbourhood",
                               "4": "neither", "5": "only position"})


class QueryFileTests(unittest.TestCase):
    def test_queries_written_from_the_real_table(self):
        table = os.path.join(ROOT, "tic_to_gaia_dr3.csv")
        if not os.path.exists(table):
            self.skipTest("table not present")
        tmp = tempfile.mkdtemp()
        try:
            d.main(["neighbourhood-queries", "--out-dir", tmp])
            files = sorted(os.listdir(tmp))
            self.assertTrue(files)
            with open(os.path.join(tmp, files[0])) as fh:
                text = fh.read()
            self.assertTrue(text.startswith("-- UNTESTED"))
            self.assertIn("gaiadr4.dr3_neighbourhood", text)
            pos = os.path.join(tmp, "pos")
            d.main(["position-queries", "--out-dir", pos])
            with open(os.path.join(pos, "expected_positions.csv")) as fh:
                rows = list(csv.DictReader(fh))
            with open(table) as fh:
                n = sum(1 for r in csv.DictReader(fh) if r["status"] in ("one-to-one", "ambiguous"))
            self.assertEqual(len(rows), n)
            with open(os.path.join(pos, "position_batch_000.adql")) as fh:
                self.assertIn("FROM gaiadr4.gaia_source WHERE", fh.read())
            # only the targets in --tic-list, on the complete tables
            lst = os.path.join(tmp, "some.txt")
            with open(lst, "w") as fh:
                fh.write("# two targets\n%s\n%s\n" % (rows[3]["tic"], rows[7]["tic"]))
            sub = os.path.join(tmp, "sub")
            d.main(["position-queries", "--out-dir", sub, "--all-sources", "--tic-list", lst])
            with open(os.path.join(sub, "expected_positions.csv")) as fh:
                got = list(csv.DictReader(fh))
            self.assertEqual([r["tic"] for r in got], sorted([rows[3]["tic"], rows[7]["tic"]],
                                                              key=lambda t: [r["tic"] for r in rows].index(t)))
            with open(os.path.join(sub, "position_batch_000.adql")) as fh:
                text = fh.read()
            self.assertTrue(text.startswith("-- UNTESTED"))
            self.assertIn("gaiadr4.all_source_astrometry", text)
            self.assertEqual(text.count("CONTAINS("), 2)
            with open(lst, "w") as fh:
                fh.write("999999999\n")
            with self.assertRaises(ValueError):
                d.main(["position-queries", "--out-dir", sub, "--tic-list", lst])
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
