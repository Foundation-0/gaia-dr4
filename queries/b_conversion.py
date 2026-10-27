"""Estimate Johnson V and B magnitudes from Gaia G, BP and RP.

Why: the Harvard plates and the DASCH archive use blue-like magnitudes. Gaia
does not measure B. Question C of this project needs "brighter than about
B = 13.5", so the cut needs an estimate of B from what Gaia does measure.

Two estimates of B are provided.

Method A, "published chain". Built only from published relations.
  1. V = G - (G - V)(BP-RP). Riello et al. 2021, A&A 649, A3, the coefficients in
     Table 8 of Appendix C of the arXiv version (arXiv:2012.01916). The A&A table number
     was not checked. Row G - V = f(G_BP - G_RP). Valid for -0.5 < BP-RP < 5.0.
     Scatter 0.030 mag (as published, on the stars of their fit).
  2. Tycho-2 colour BT - VT from two relations of the same table:
       G - VT = f(BP-RP)  (valid -0.35 < BP-RP < 4.0, scatter 0.054)
       G - BT = f(BP-RP)  (valid -0.3 < BP-RP < 3.0, scatter 0.071)
       BT - VT = (G - VT) - (G - BT)
     The validity ranges are in Table 7 of the same appendix (arXiv version).
  3. B - V = 0.850 (BT - VT). ESA SP-1200 (1997), section 2.2, Eq. 2.2.2. Valid
     for -0.2 < BT - VT < 1.8, systematic error up to 0.05 mag in B - V, stated
     for unreddened main-sequence stars only.
  4. B = V + (B - V).
  Riello et al. publish no direct Johnson B relation, so step 2 and 3 are needed.
  Some of Riello's other relations are marked as valid only for M giants at red
  colours. The ones used here carry no such mark, but the ESA step was derived for
  main-sequence stars. The validity ranges above are written here only: the code
  does not enforce them (see "The ADQL cut" in README.md).

Method B, "APASS fit". B - V is a cubic polynomial in BP-RP fitted by us to
  stars with APASS DR9 B and V magnitudes (see validate_b.py and results/).
  V is still taken from step 1 of method A. It is a local calibration, valid
  where the fitting sample has stars.

Every function works on plain floats, so it can be tested without any data.
`adql_*` functions write the same formulas as ADQL text, so the query and the
Python code cannot drift apart (test_b_conversion.py checks this).
"""

# Riello et al. 2021, Table 8 of Appendix C (arXiv version): polynomial coefficients, lowest power first.
GV_FROM_BPRP = (-0.02704, 0.01424, -0.2156, 0.01426)            # G - V
GVT_FROM_BPRP = (-0.01077, -0.0682, -0.2387, 0.02342)            # G - VT
GBT_FROM_BPRP = (-0.004288, -0.8547, 0.1244, -0.9085, 0.4843, -0.06814)  # G - BT

# ESA SP-1200 section 2.2, Eq. 2.2.2
BV_PER_BTVT = 0.850

# Method B: B - V = sum(c[i] * (BP-RP)**i). Filled in from results/b_minus_v_fit.json
# by validate_b.py. See that file for the sample size, date and fit statistics.
BV_APASS_FIT = (-0.006829, 0.609467, 0.280520, -0.082327)

# The cut "brighter than B = 13.5", written so that it keeps every star that might truly pass.
# The margins are choices, not a derived rule. MARGIN_BLUE is the largest "too faint" error of
# method A on the blue test stars (+0.18), rounded up to 0.25. MARGIN_RED (0.50) is about twice the
# largest too-faint error in its bin (+0.23), a chosen value. MIN_B_MINUS_G_VERY_RED is the smallest
# B - G seen (2.71), rounded down. The no-colour value is a guess. The blue and red margins were
# checked on 200 train stars and 100 bright red stars (results/b_validation.md). Details in README.md.
B_LIMIT = 13.5
RED_EDGE_1 = 2.0         # BP-RP below this: the published chain works (bias +0.01, scatter 0.05)
RED_EDGE_2 = 2.5         # BP-RP from here on: the chain fails, B is bounded from G alone
MARGIN_BLUE = 0.25       # BP-RP < 2.0
MARGIN_RED = 0.5         # 2.0 <= BP-RP < 2.5
# Smallest B - G among the 100 sample stars with BP-RP >= 2.5 (50 main sample, 50 bright red) was 2.71.
MIN_B_MINUS_G_VERY_RED = 2.5
# Used when BP-RP is missing. A rounded guess for the hottest stars, NOT tested: the sample has
# only 2 stars with BP-RP below 0 and the smallest B - G in its bluest bin (BP-RP below 0.3) was 0.00.
MIN_B_MINUS_G_NO_COLOUR = -0.3


def poly(coeffs, x):
    """Polynomial with the lowest power first, by Horner's rule."""
    total = 0.0
    for c in reversed(coeffs):
        total = total * x + c
    return total


def v_mag(g, bp_rp):
    """Johnson V from Gaia G and BP-RP (Riello et al. 2021)."""
    return g - poly(GV_FROM_BPRP, bp_rp)


def btvt_published(bp_rp):
    """Tycho-2 BT - VT from BP-RP (difference of two Riello et al. 2021 relations)."""
    return poly(GVT_FROM_BPRP, bp_rp) - poly(GBT_FROM_BPRP, bp_rp)


def bv_published(bp_rp):
    """Johnson B - V by method A."""
    return BV_PER_BTVT * btvt_published(bp_rp)


def b_mag_published(g, bp_rp):
    """Johnson B by method A."""
    return v_mag(g, bp_rp) + bv_published(bp_rp)


def bv_fit(bp_rp, coeffs=None):
    """Johnson B - V by method B."""
    c = coeffs if coeffs is not None else BV_APASS_FIT
    if c is None:
        raise ValueError("BV_APASS_FIT has not been set")
    return poly(c, bp_rp)


def b_mag_fit(g, bp_rp, coeffs=None):
    """Johnson B by method B."""
    return v_mag(g, bp_rp) + bv_fit(bp_rp, coeffs)


def passes_bcut(g, bp_rp, b_limit=B_LIMIT):
    """Python twin of the ADQL cut from `adql_bcut`. True if the star may have B < b_limit."""
    if bp_rp is None:
        return g + MIN_B_MINUS_G_NO_COLOUR < b_limit
    if bp_rp < RED_EDGE_1:
        return b_mag_published(g, bp_rp) < b_limit + MARGIN_BLUE
    if bp_rp < RED_EDGE_2:
        return b_mag_published(g, bp_rp) < b_limit + MARGIN_RED
    return g + MIN_B_MINUS_G_VERY_RED < b_limit


# ---- the same formulas as ADQL text -------------------------------------------------------

def _adql_poly(coeffs, x):
    """ADQL text for a polynomial in `x`, with plain multiplications (no POWER)."""
    out = ""
    for i, c in enumerate(coeffs):
        c = float(c)
        body = repr(abs(c)) if i == 0 else "%r*%s" % (abs(c), "*".join([x] * i))
        if i == 0:
            out += ("-" if c < 0 else "") + body
        else:
            out += (" - " if c < 0 else " + ") + body
    return "(" + out + ")"


def adql_v(g="gs.phot_g_mean_mag", c="gs.bp_rp"):
    return "(%s - %s)" % (g, _adql_poly(GV_FROM_BPRP, c))


def adql_bv_published(c="gs.bp_rp"):
    return "(%r*(%s - %s))" % (BV_PER_BTVT, _adql_poly(GVT_FROM_BPRP, c), _adql_poly(GBT_FROM_BPRP, c))


def adql_bv_fit(c="gs.bp_rp", coeffs=None):
    cf = coeffs if coeffs is not None else BV_APASS_FIT
    return _adql_poly(cf, c)


def adql_b(method, g="gs.phot_g_mean_mag", c="gs.bp_rp"):
    """ADQL text for the B estimate. method is 'published' or 'fit'."""
    if method == "published":
        return "(%s + %s)" % (adql_v(g, c), adql_bv_published(c))
    if method == "fit":
        return "(%s + %s)" % (adql_v(g, c), adql_bv_fit(c))
    raise ValueError(method)


def adql_bcut(g="gs.phot_g_mean_mag", c="gs.bp_rp", b_limit=B_LIMIT):
    """ADQL text of the cut. Four branches: normal colours, red colours, very red, no colour."""
    b = adql_b("published", g, c)
    return (
        "(({c} < {e1} AND {b} < {l1})\n"
        "    OR ({c} >= {e1} AND {c} < {e2} AND {b} < {l2})\n"
        "    OR ({c} >= {e2} AND {g} + {m3} < {lim})\n"
        "    OR ({c} IS NULL AND {g} + ({m4}) < {lim}))"
    ).format(c=c, g=g, b=b, e1=RED_EDGE_1, e2=RED_EDGE_2, lim=b_limit,
             l1=round(b_limit + MARGIN_BLUE, 6), l2=round(b_limit + MARGIN_RED, 6),
             m3=MIN_B_MINUS_G_VERY_RED, m4=MIN_B_MINUS_G_NO_COLOUR)
