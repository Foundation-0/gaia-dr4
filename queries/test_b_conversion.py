"""Tests for b_conversion.py. They need no network and no downloaded data."""
import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import b_conversion as bc  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def eval_adql(expr, g, c):
    """Evaluate an ADQL arithmetic expression from adql_* by turning the column names into numbers."""
    py = expr.replace("gs.phot_g_mean_mag", repr(g)).replace("gs.bp_rp", "(%r)" % c)
    assert re.fullmatch(r"[0-9eE+\-*/(). ]+", py), py
    return eval(py)  # noqa: S307 - only digits and arithmetic signs pass the check above


class PolynomialTests(unittest.TestCase):
    def test_horner_matches_direct_sum(self):
        c = (1.0, -2.0, 0.5, 3.0)
        for x in (-1.5, 0.0, 0.7, 2.2):
            self.assertAlmostEqual(bc.poly(c, x), sum(a * x ** i for i, a in enumerate(c)), places=12)

    def test_v_for_a_solar_colour(self):
        # BP-RP = 0.82 (solar type): G - V = -0.02704 + 0.01424*0.82 - 0.2156*0.82**2 + 0.01426*0.82**3 = -0.1521
        self.assertAlmostEqual(12.0 - bc.v_mag(12.0, 0.82), -0.15247, places=4)

    def test_riello_coefficients_as_published(self):
        # Riello et al. 2021, Table 8 of Appendix C (arXiv version), row G - V = f(BP-RP)
        self.assertEqual(bc.GV_FROM_BPRP, (-0.02704, 0.01424, -0.2156, 0.01426))
        self.assertEqual(bc.GVT_FROM_BPRP, (-0.01077, -0.0682, -0.2387, 0.02342))
        self.assertEqual(bc.GBT_FROM_BPRP, (-0.004288, -0.8547, 0.1244, -0.9085, 0.4843, -0.06814))

    def test_published_chain_for_a_solar_colour(self):
        # BT - VT = 0.714 at BP-RP = 0.82, so B - V = 0.85 * 0.714 = 0.607 (the Sun has 0.65)
        self.assertAlmostEqual(bc.bv_published(0.82), 0.607, places=2)
        self.assertAlmostEqual(bc.bv_published(0.0), -0.006, places=2)

    def test_chain_has_the_right_sign(self):
        for c in (0.2, 0.8, 1.4):
            self.assertGreater(bc.bv_published(c), 0.0)   # redder stars have larger B - V
        self.assertLess(bc.bv_published(1.4), 1.6)


class AdqlTextTests(unittest.TestCase):
    def test_v_expression_equals_python(self):
        for g, c in [(10.0, 0.3), (12.5, 1.2), (13.1, 2.4), (9.0, -0.1)]:
            self.assertAlmostEqual(eval_adql(bc.adql_v(), g, c), bc.v_mag(g, c), places=9)

    def test_published_b_expression_equals_python(self):
        for g, c in [(10.0, 0.3), (12.5, 1.2), (13.1, 2.4), (9.0, -0.1), (11.0, 3.2)]:
            self.assertAlmostEqual(eval_adql(bc.adql_b("published"), g, c), bc.b_mag_published(g, c), places=9)

    def test_fit_b_expression_equals_python(self):
        for g, c in [(10.0, 0.3), (12.5, 1.2), (13.1, 2.4)]:
            self.assertAlmostEqual(eval_adql(bc.adql_b("fit"), g, c), bc.b_mag_fit(g, c), places=9)

    def test_no_power_function_and_no_unary_plus_minus(self):
        text = bc.adql_b("published") + bc.adql_bcut()
        self.assertNotIn("POWER", text)
        self.assertNotIn("+ -", text)
        self.assertNotIn("- -", text)

    def test_cut_text_has_four_branches(self):
        cut = bc.adql_bcut()
        self.assertEqual(cut.count("gs.bp_rp IS NULL"), 1)
        self.assertIn("gs.bp_rp < 2.0", cut)
        self.assertIn("gs.bp_rp >= 2.5", cut)
        self.assertIn("13.75", cut)
        self.assertIn("14.0", cut)


class CutBehaviourTests(unittest.TestCase):
    def test_normal_colour_margin(self):
        # a star with an estimated B of 13.6 passes (limit 13.75); one at 13.9 does not
        g = 12.9
        c = 0.9
        b = bc.b_mag_published(g, c)
        self.assertTrue(bc.passes_bcut(g + (13.6 - b), c))
        self.assertFalse(bc.passes_bcut(g + (13.9 - b), c))

    def test_very_red_uses_g_only(self):
        self.assertTrue(bc.passes_bcut(10.9, 3.0))
        self.assertFalse(bc.passes_bcut(11.2, 3.0))

    def test_missing_colour(self):
        self.assertTrue(bc.passes_bcut(13.7, None))
        self.assertFalse(bc.passes_bcut(13.9, None))

    def test_red_branch_margin(self):
        g = 11.0
        c = 2.2
        b = bc.b_mag_published(g, c)
        self.assertTrue(bc.passes_bcut(g + (13.9 - b), c))
        self.assertFalse(bc.passes_bcut(g + (14.1 - b), c))


class FitFileTests(unittest.TestCase):
    def test_constant_matches_the_fit_file(self):
        with open(os.path.join(HERE, "results", "b_minus_v_fit.json")) as f:
            fit = json.load(f)["coefficients"]
        self.assertEqual(len(fit), len(bc.BV_APASS_FIT))
        for a, b in zip(fit, bc.BV_APASS_FIT):
            self.assertAlmostEqual(a, b, places=6)


if __name__ == "__main__":
    unittest.main()
