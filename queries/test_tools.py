"""Tests for the small tools: the data model parser, the stand-in maker and the statistics helpers.
No network, no downloaded data."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_queries as bq  # noqa: E402
import check_columns as cc  # noqa: E402
import datamodel_columns as dm  # noqa: E402
import make_standin as ms  # noqa: E402
import validate_b as vb  # noqa: E402

SAMPLE_MODEL = """
Contents
18.6 vari_eclipsing_binary [TAP]  . . . . 1086
18.7 vari_epoch_flags [DataLink]  . . . . 1098

18.6 vari_eclipsing_binary [TAP]
This table describes eclipsing binaries.
D
Columns description:
source_id : Unique source identifier (long)
A unique single numerical identifier.
ra
reference_time : Reference time used for the geometric model fit (double, Time[Barycentric
JD in TCB − 2 455 197.5 (day)])
Time with respect to which the phases refer.
frequency : Frequency of geometric model of the eclipsing binary light curve (double, Frequency[day−1 ])
Frequency.
Gaia DPAC Document                      Gaia DPAC CU9                  1086
geom_model_reference_level_error : Uncertainty on magnitude reference level of ge-
ometric model (float, Magnitude[mag])
Uncertainty.
18.7 vari_epoch_flags [DataLink]
other_column : Something (long)
"""

MAP = (
    "kind\tdr4_table\tdr4_name\tdr3_table\tdr3_name\tdr4_unit\tdr3_unit\tdr4_type\tdr3_type\tstatus\tunit_check\tnotes\n"
    "table\tgaiadr4.big\t-\tgaiadr3.big\t-\t\t\t\t\tsame\tn/a\t\n"
    "table\tgaiadr4.nb\t-\tgaiadr3.old_nb\t-\t\t\t\t\trenamed\tn/a\t\n"
    "column\tbig\tsource_id\tbig\tsource_id\t\t\t\t\tsame\tn/a\t\n"
    "column\tbig\tteff\tbig\tteff_gspphot\t\t\t\t\trenamed\tn/a\t\n"
    "column\tbig\tonly4\tbig\t-\t\t\t\t\tdr4_only\tn/a\t\n"
    "column\tnb\tsource_id\told_nb\tdr3_source_id\t\t\t\t\trenamed\tn/a\t\n"
    "column\tnb\tdr3_source_id\told_nb\tdr2_source_id\t\t\t\t\trenamed\tn/a\t\n"
)


class DataModelParserTests(unittest.TestCase):
    def setUp(self):
        lines = dm.clean_lines(SAMPLE_MODEL)
        self.cols = {c["column"]: c for c in dm.parse_columns(dm.section(lines, "vari_eclipsing_binary"))}

    def test_finds_the_columns_of_the_right_section_only(self):
        self.assertEqual(set(self.cols), {"source_id", "reference_time", "frequency", "geom_model_reference_level_error"})

    def test_type_and_unit(self):
        self.assertEqual(self.cols["source_id"]["type"], "long")
        self.assertEqual(self.cols["frequency"]["type"], "double")
        self.assertIn("day", self.cols["frequency"]["unit"])

    def test_nested_parentheses_in_the_unit(self):
        self.assertEqual(self.cols["reference_time"]["type"], "double")
        self.assertIn("2 455 197.5", self.cols["reference_time"]["unit"])

    def test_wrapped_heading_with_hyphen_break(self):
        c = self.cols["geom_model_reference_level_error"]
        self.assertEqual(c["type"], "float")
        self.assertEqual(c["unit"], "mag")
        self.assertIn("geometric", c["title"])

    def test_committed_tsv_has_the_two_tables(self):
        here = os.path.dirname(os.path.abspath(__file__))
        counts = {}
        with open(os.path.join(here, "datamodel", "dr4_draft_columns.tsv"), encoding="utf-8") as f:
            next(f)
            for line in f:
                t, col = line.split("\t")[:2]
                counts.setdefault(t, set()).add(col)
        self.assertEqual(len(counts["vari_planetary_transit"]), 7)
        self.assertEqual(len(counts["vari_eclipsing_binary"]), 50)
        for c in ("transit_reference_time", "transit_period", "transit_depth", "transit_duration", "num_in_transit"):
            self.assertIn(c, counts["vari_planetary_transit"])
        for c in ("frequency", "reference_time", "derived_primary_ecl_phase", "model_type"):
            self.assertIn(c, counts["vari_eclipsing_binary"])


class StandInTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False, encoding="utf-8")
        self.tmp.write(MAP)
        self.tmp.close()

    def tearDown(self):
        os.unlink(self.tmp.name)

    def conv(self, text):
        return ms.convert(text, self.tmp.name)

    def test_table_and_column_rename(self):
        out = self.conv("SELECT b.source_id, b.teff\nFROM gaiadr4.big AS b\nWHERE b.teff > 1")
        self.assertIn("FROM gaiadr3.big AS b", out)
        self.assertIn("b.teff_gspphot", out)
        self.assertNotIn("gaiadr4", out)

    def test_swapped_names_are_renamed_at_once(self):
        out = self.conv("SELECT n.source_id, n.dr3_source_id\nFROM gaiadr4.nb AS n")
        self.assertIn("n.dr3_source_id, n.dr2_source_id", out)
        self.assertIn("gaiadr3.old_nb", out)

    def test_dr4only_lines_are_dropped(self):
        out = self.conv("SELECT b.source_id,\n b.only4,  -- DR4ONLY\n b.teff\nFROM gaiadr4.big AS b")
        self.assertNotIn("only4", out)
        self.assertIn("b.source_id,", out)

    def test_comments_are_removed(self):
        out = self.conv("-- header\nSELECT b.source_id -- note\nFROM gaiadr4.big AS b")
        self.assertNotIn("--", out)

    def test_numbers_and_functions_untouched(self):
        out = self.conv("SELECT FLOOR(LOG10(1.0 / b.teff) * 4.0) AS x\nFROM gaiadr4.big AS b WHERE b.teff < 0.01")
        self.assertIn("FLOOR(LOG10(1.0 / b.teff_gspphot) * 4.0)", out)
        self.assertIn("0.01", out)

    def test_unknown_column_stops(self):
        with self.assertRaises(ValueError):
            self.conv("SELECT b.nope\nFROM gaiadr4.big AS b")

    def test_untagged_dr4only_column_stops(self):
        with self.assertRaises(ValueError):
            self.conv("SELECT b.source_id, b.only4\nFROM gaiadr4.big AS b")

    def test_tagged_column_with_equivalent_stops(self):
        with self.assertRaises(ValueError):
            self.conv("SELECT b.source_id,  -- DR4ONLY\n b.teff\nFROM gaiadr4.big AS b")

    def test_trailing_comma_stops(self):
        with self.assertRaises(ValueError):
            self.conv("SELECT b.source_id,\n b.only4,  -- DR4ONLY\nFROM gaiadr4.big AS b")

    def test_table_without_alias_stops(self):
        with self.assertRaises(ValueError):
            self.conv("SELECT b.teff\nFROM gaiadr4.big AS b\nJOIN gaiadr4.nb nb ON nb.source_id = b.source_id")

    def test_unknown_qualifier_stops(self):
        with self.assertRaises(ValueError):
            self.conv("SELECT zz.teff\nFROM gaiadr4.big AS b")


class NameCheckTests(unittest.TestCase):
    def test_table_without_alias_is_reported(self):
        problems = cc.name_problems("SELECT gs.ra\nFROM gaiadr3.gaia_source gs")
        self.assertTrue(any("without an AS alias" in p for p in problems))

    def test_unknown_qualifier_is_reported(self):
        problems = cc.name_problems("SELECT gs.ra, zz.dec\nFROM gaiadr3.gaia_source AS gs")
        self.assertEqual(len(problems), 1)
        self.assertIn("zz.dec", problems[0])

    def test_subquery_alias_and_output_names_are_fine(self):
        text = ("SELECT gs.ra, t.n\nFROM gaiadr3.gaia_source AS gs\nJOIN (\n    SELECT 1 AS n\n"
                "    FROM gaiadr3.gaia_source AS x\n) AS t ON 1 = 1")
        self.assertEqual(cc.name_problems(text), [])


class WrapTests(unittest.TestCase):
    def test_long_word_is_cut_and_the_loop_ends(self):
        out = bq.wrap(["x" * 130])
        self.assertTrue(all(len(line) <= bq.WRAP_WIDTH for line in out))
        rebuilt = out[0] + "".join(line[len(bq.WRAP_PREFIX):] for line in out[1:])
        self.assertEqual(rebuilt, "x" * 130)

    def test_long_line_breaks_between_words(self):
        words = ["word%02d" % i for i in range(40)]
        out = bq.wrap(["-- " + " ".join(words)])
        self.assertTrue(all(len(line) <= bq.WRAP_WIDTH for line in out))
        tokens = " ".join(out).split()
        for w in words:
            self.assertIn(w, tokens)

    def test_short_line_is_unchanged(self):
        self.assertEqual(bq.wrap(["-- short"]), ["-- short"])


class StatsTests(unittest.TestCase):
    def test_stats(self):
        s = vb.stats([-1.0, 0.0, 1.0, 2.0, 3.0])
        self.assertEqual(s["n"], 5)
        self.assertAlmostEqual(s["mean"], 1.0)
        self.assertAlmostEqual(s["median"], 1.0)
        self.assertAlmostEqual(s["std"], 1.5811388, places=6)
        self.assertEqual(s["worst_fainter"], 3.0)
        self.assertEqual(s["worst_brighter"], -1.0)

    def test_robust_scatter_ignores_a_wild_value(self):
        s = vb.stats([0.0, 0.1, -0.1, 0.05, -0.05, 9.0])
        self.assertLess(s["robust_std"], 0.2)
        self.assertGreater(s["std"], 3.0)

    def test_polynomial_fit_recovers_coefficients(self):
        xs = [i / 10.0 for i in range(-5, 30)]
        ys = [0.1 + 0.6 * x + 0.3 * x ** 2 - 0.08 * x ** 3 for x in xs]
        c = vb.lstsq_poly(xs, ys, 3)
        for a, b in zip(c, (0.1, 0.6, 0.3, -0.08)):
            self.assertAlmostEqual(a, b, places=6)


if __name__ == "__main__":
    unittest.main()
