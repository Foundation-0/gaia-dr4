import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from astrometry import propagate, separation_arcsec  # noqa: E402


class PropagateTests(unittest.TestCase):
    def test_zero_years_changes_nothing(self):
        self.assertEqual(propagate(10.0, 20.0, 500.0, -300.0, 0.0), (10.0, 20.0))

    def test_declination_motion(self):
        ra, dec = propagate(10.0, 0.0, 0.0, 1000.0, 1.0)  # 1 arcsec in one year
        self.assertAlmostEqual(dec, 1.0 / 3600.0, places=12)
        self.assertEqual(ra, 10.0)

    def test_right_ascension_motion_is_on_the_sky(self):
        # pmra already contains cos(dec), so at dec 60 the change in ra doubles.
        ra, dec = propagate(10.0, 60.0, 1000.0, 0.0, 1.0)
        self.assertAlmostEqual(ra - 10.0, 2.0 / 3600.0, places=9)
        self.assertEqual(dec, 60.0)

    def test_going_back_in_time(self):
        ra, dec = propagate(10.0, 0.0, 1000.0, 1000.0, -16.0)
        self.assertAlmostEqual(ra, 10.0 - 16.0 / 3600.0, places=9)
        self.assertAlmostEqual(dec, -16.0 / 3600.0, places=9)

    def test_missing_proper_motion_leaves_position(self):
        self.assertEqual(propagate(10.0, 20.0, None, 5.0, 10.0), (10.0, 20.0))
        self.assertEqual(propagate(10.0, 20.0, 5.0, None, 10.0), (10.0, 20.0))

    def test_right_ascension_wraps_past_360(self):
        # 1 arcsec = 0.000277778 degree east of 359.9999 is 0.000177778 degree past zero
        ra, _ = propagate(359.9999, 0.0, 1000.0, 0.0, 1.0)
        self.assertAlmostEqual(ra, 0.0001777778, places=8)

    def test_right_ascension_wraps_below_zero(self):
        ra, _ = propagate(0.0001, 0.0, -1000.0, 0.0, 1.0)
        self.assertAlmostEqual(ra, 360.0 - 0.0001777778, places=8)


class SeparationTests(unittest.TestCase):
    def test_same_point(self):
        self.assertEqual(separation_arcsec(10, 20, 10, 20), 0.0)

    def test_one_arcsecond_in_declination(self):
        self.assertAlmostEqual(separation_arcsec(10, 20, 10, 20 + 1 / 3600), 1.0, places=6)

    def test_right_ascension_offset_shrinks_with_cos_dec(self):
        self.assertAlmostEqual(separation_arcsec(10, 60, 10 + 2 / 3600, 60), 1.0, places=4)

    def test_across_zero_of_right_ascension(self):
        self.assertAlmostEqual(separation_arcsec(359.99999, 0, 0.00001, 0), 0.072, places=3)

    def test_opposite_points(self):
        self.assertAlmostEqual(separation_arcsec(0, 0, 180, 0), 180 * 3600, places=3)


if __name__ == "__main__":
    unittest.main()
