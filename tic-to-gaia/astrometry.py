"""Small sky-position helpers, written with the standard library only.

Positions are in degrees, proper motions in milliarcseconds per year (mas/yr), epochs in
Julian years. Gaia's `pmra` already includes the cos(dec) factor (it is the motion on the
sky, not the change in right ascension), and so does the TESS Input Catalog's `pmra`.

The propagation is linear on the sky. Over the 16 years used here, for a star moving
1 arcsecond a year, the neglected curvature terms are about 1 milliarcsecond (mas). That
is far below the limits used to judge a match (0.2 arcsecond and up), so it does not matter
for this task. Parallax and radial velocity are ignored for the same reason.
"""

import math

MAS_PER_DEG = 3.6e6


def propagate(ra, dec, pmra, pmdec, years):
    """Move a position by `years` of proper motion. Returns (ra, dec) in degrees.

    pmra or pmdec of None means "no proper motion known": the position is returned
    unchanged.
    """
    if pmra is None or pmdec is None:
        return ra, dec
    cosd = math.cos(math.radians(dec))
    if abs(cosd) < 1e-9:  # at a pole, right ascension is undefined
        return ra, dec
    new_ra = ra + pmra * years / MAS_PER_DEG / cosd
    new_dec = dec + pmdec * years / MAS_PER_DEG
    return new_ra % 360.0, new_dec


def separation_arcsec(ra1, dec1, ra2, dec2):
    """Angle between two positions in arcseconds (haversine formula)."""
    p1, p2 = math.radians(dec1), math.radians(dec2)
    dp = p2 - p1
    dl = math.radians(ra2 - ra1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    a = min(1.0, max(0.0, a))
    return math.degrees(2 * math.asin(math.sqrt(a))) * 3600.0
