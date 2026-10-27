"""Check the Gaia-to-Johnson conversion against stars with measured B.

Measured B comes from APASS DR9 (Johnson B and V, calibrated to Landolt
standards; Henden et al. 2016, VizieR II/336). The Gaia archive holds a copy of
APASS DR9 (`external.apassdr9`) and an official cross-match to Gaia DR3
(`gaiadr3.apassdr9_best_neighbour`), so the whole sample comes from one service.

Steps (each step caches its answers, so a re-run makes no new requests):

    python3 -I validate_b.py sample     # 8 colour bins x 50 stars -> results/b_sample.csv
    python3 -I validate_b.py fit        # fit method B on the "train" half -> results/b_minus_v_fit.json
    python3 -I validate_b.py report     # bias and scatter on the "test" half -> results/b_validation.md

The sample is stratified in BP-RP so that red and blue stars are tested as well
as the common solar-type stars. In each bin the 50 stars with the smallest
`random_index` (a fixed pseudo-random number every Gaia source carries) are
taken. The first 25 of them are the TEST stars (8 x 25 = 200). The next 25 are
the TRAIN stars, used only to fit method B. A star is never in both.
"""
import csv
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import b_conversion as bc  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")
SAMPLE = os.path.join(RESULTS, "b_sample.csv")
FIT = os.path.join(RESULTS, "b_minus_v_fit.json")

# BP-RP bins: low edge included, high edge excluded
BINS = [(-0.5, 0.3), (0.3, 0.6), (0.6, 0.9), (0.9, 1.2), (1.2, 1.6), (1.6, 2.0), (2.0, 2.5), (2.5, 5.0)]
GROUPS = [("all, BP-RP below 2.0", -9.0, 2.0), ("all, BP-RP 2.0 to 2.5", 2.0, 2.5),
          ("all, BP-RP 2.5 and above", 2.5, 99.0), ("all test stars", -9.0, 99.0)]
# Extra red stars, brighter than the main sample. A red star needs G below about 11 to have B < 13.5, so
# the main sample (G 10 to 14) holds few of them. These stars check the red end of the cut.
RED_BRIGHT_BINS = [(2.0, 2.5), (2.5, 5.0)]
RED_BRIGHT_G = (8.0, 11.0)
PER_BIN = 50
N_TEST = 25
G_RANGE = (10.0, 14.0)   # APASS saturates for stars brighter than about V = 10
RANDOM_INDEX_MAX = 30000000

QUERY = """SELECT TOP {top} gs.source_id, gs.ra, gs.dec, gs.random_index,
  gs.phot_g_mean_mag, gs.phot_bp_mean_mag, gs.phot_rp_mean_mag, gs.bp_rp,
  gs.phot_bp_rp_excess_factor, gs.ruwe,
  ap.vmag, ap.e_vmag, ap.bmag, ap.e_bmag, ap.nobs, xm.angular_distance
FROM gaiadr3.gaia_source AS gs
JOIN gaiadr3.apassdr9_best_neighbour AS xm ON xm.source_id = gs.source_id
JOIN external.apassdr9 AS ap ON ap.recno = xm.original_ext_source_id
WHERE gs.random_index < {rimax}
  AND gs.phot_g_mean_mag BETWEEN {g0} AND {g1}
  AND gs.bp_rp >= {c0} AND gs.bp_rp < {c1}
  AND xm.number_of_neighbours = 1 AND xm.number_of_mates = 0 AND xm.angular_distance < 1.0
  AND ap.e_vmag > 0 AND ap.e_bmag > 0 AND ap.e_vmag < 0.06 AND ap.e_bmag < 0.06 AND ap.nobs >= 3
ORDER BY gs.random_index"""


def fetch_sample():
    rows_out = []
    header = None
    for i, (c0, c1) in enumerate(BINS):
        q = QUERY.format(top=PER_BIN, rimax=RANDOM_INDEX_MAX, g0=G_RANGE[0], g1=G_RANGE[1], c0=c0, c1=c1)
        h, rows = common.tap_query(q, note="B validation sample, BP-RP bin %s..%s" % (c0, c1))
        header = h
        print("bin %s..%s: %d stars" % (c0, c1, len(rows)))
        for k, r in enumerate(rows):
            rows_out.append([i, "test" if k < N_TEST else "train"] + r)
    for j, (c0, c1) in enumerate(RED_BRIGHT_BINS):
        q = QUERY.format(top=PER_BIN, rimax=RANDOM_INDEX_MAX, g0=RED_BRIGHT_G[0], g1=RED_BRIGHT_G[1], c0=c0, c1=c1)
        h, rows = common.tap_query(q, note="B validation, bright red stars, BP-RP bin %s..%s" % (c0, c1))
        print("bright red bin %s..%s: %d stars" % (c0, c1, len(rows)))
        for r in rows:
            rows_out.append([len(BINS) + j, "redbright"] + r)
    os.makedirs(RESULTS, exist_ok=True)
    with open(SAMPLE, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["bin", "role"] + header)
        w.writerows(rows_out)
    print("wrote", SAMPLE, len(rows_out))


def load_sample():
    out = []
    with open(SAMPLE) as f:
        for r in csv.DictReader(f):
            d = {k: (float(v) if v not in ("", "null") and k not in ("role",) else v) for k, v in r.items()}
            d["role"] = r["role"]
            out.append(d)
    return out


def lstsq_poly(x, y, degree):
    """Least-squares polynomial (lowest power first), solved with normal equations in plain Python."""
    n = degree + 1
    a = [[sum(xi ** (i + j) for xi in x) for j in range(n)] for i in range(n)]
    b = [sum(yi * xi ** i for xi, yi in zip(x, y)) for i in range(n)]
    for col in range(n):                       # Gaussian elimination with partial pivoting
        piv = max(range(col, n), key=lambda r: abs(a[r][col]))
        a[col], a[piv] = a[piv], a[col]
        b[col], b[piv] = b[piv], b[col]
        for r in range(col + 1, n):
            f = a[r][col] / a[col][col]
            for k in range(col, n):
                a[r][k] -= f * a[col][k]
            b[r] -= f * b[col]
    coef = [0.0] * n
    for r in range(n - 1, -1, -1):
        coef[r] = (b[r] - sum(a[r][k] * coef[k] for k in range(r + 1, n))) / a[r][r]
    return coef


def stats(d):
    """Bias (mean), standard deviation and robust scatter (1.4826 x median absolute deviation)."""
    n = len(d)
    if n == 0:
        return {"n": 0}
    m = sum(d) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in d) / (n - 1)) if n > 1 else float("nan")
    s = sorted(d)
    med = s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])
    mad = sorted(abs(x - med) for x in d)
    mad_med = mad[n // 2] if n % 2 else 0.5 * (mad[n // 2 - 1] + mad[n // 2])
    return {"n": n, "mean": m, "median": med, "std": sd, "robust_std": 1.4826 * mad_med,
            "worst_fainter": max(d), "worst_brighter": min(d)}


def fit(degree=3):
    sample = [r for r in load_sample() if r["role"] == "train"]
    x = [r["bp_rp"] for r in sample]
    y = [r["bmag"] - r["vmag"] for r in sample]
    coef = lstsq_poly(x, y, degree)
    for _ in range(2):  # drop > 3 sigma outliers, twice
        res = [yi - bc.poly(coef, xi) for xi, yi in zip(x, y)]
        sd = stats(res)["std"]
        keep = [i for i, e in enumerate(res) if abs(e) < 3 * sd]
        coef = lstsq_poly([x[i] for i in keep], [y[i] for i in keep], degree)
    res = [yi - bc.poly(coef, xi) for xi, yi in zip(x, y)]
    out = {"what": "B - V = sum(c[i] * (BP-RP)**i), fitted to APASS DR9 B-V of the train stars",
           "coefficients": coef, "degree": degree, "n_train": len(sample), "n_used": len(keep),
           "bp_rp_range": [min(x), max(x)], "rms_residual_all_train": stats(res)["std"],
           "sample_file": "results/b_sample.csv"}
    with open(FIT, "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out, indent=1))


def load_fit():
    with open(FIT) as f:
        return json.load(f)["coefficients"]


def report():
    coef = load_fit()
    test = [r for r in load_sample() if r["role"] == "test"]
    lines = []
    out = lines.append
    out("# B conversion check: results\n")
    out("Test sample: %d stars from APASS DR9 (Johnson B, V) matched to Gaia DR3, G between %s and %s, "
        "%d colour bins of 25 stars.\n" % (len(test), G_RANGE[0], G_RANGE[1], len(BINS)))
    out("Differences are estimate minus APASS, in magnitudes. `robust` is 1.4826 x the median absolute "
        "deviation, which ignores a few wild stars. A positive difference means the estimate is fainter than APASS. "
        "'Most too faint' and 'most too bright' are the largest differences in each direction.\n")

    def block(title, fn_est, selector):
        out("\n## %s\n" % title)
        out("| BP-RP | n | bias | median | std | robust | most too faint | most too bright |")
        out("|---|---|---|---|---|---|---|---|")

        def row(label, d):
            s = stats(d)
            out("| %s | %d | %+.3f | %+.3f | %.3f | %.3f | %+.2f | %+.2f |" % (
                label, s["n"], s["mean"], s["median"], s["std"], s["robust_std"],
                s["worst_fainter"], s["worst_brighter"]))

        for i, (c0, c1) in enumerate(BINS):
            row("%.1f to %.1f" % (c0, c1), [fn_est(r) - selector(r) for r in test if int(r["bin"]) == i])
        for label, lo, hi in GROUPS:
            row("**%s**" % label, [fn_est(r) - selector(r) for r in test if lo <= r["bp_rp"] < hi])

    block("V from Riello et al. 2021 (G - V relation)", lambda r: bc.v_mag(r["phot_g_mean_mag"], r["bp_rp"]),
          lambda r: r["vmag"])
    block("B, method A (published chain)", lambda r: bc.b_mag_published(r["phot_g_mean_mag"], r["bp_rp"]),
          lambda r: r["bmag"])
    block("B, method B (cubic B - V fit to APASS, other stars)",
          lambda r: bc.b_mag_fit(r["phot_g_mean_mag"], r["bp_rp"], coef), lambda r: r["bmag"])
    block("B - V, method A", lambda r: bc.bv_published(r["bp_rp"]), lambda r: r["bmag"] - r["vmag"])
    block("B - V, method B", lambda r: bc.bv_fit(r["bp_rp"], coef), lambda r: r["bmag"] - r["vmag"])

    # Effect of the proposed cut. Method A uses no fitted numbers, so all 400 stars can be used.
    # The margins were chosen from the test stars; the train stars are an independent check.
    out("\n## The proposed cut (method A with margins, see README.md)\n")
    out("Share of stars with APASS B below 13.5 that the cut keeps, and how many fainter stars it lets in. "
        "'test' stars chose the margins. 'train' stars are an independent check.\n")
    out("| BP-RP | role | APASS B < 13.5: kept | share | APASS B >= 13.5: let in |")
    out("|---|---|---|---|---|")
    allrows = load_sample()
    for label, lo, hi in GROUPS:
        for role in ("test", "train"):
            sel = [r for r in allrows if r["role"] == role and lo <= r["bp_rp"] < hi]
            tin = [r for r in sel if r["bmag"] < bc.B_LIMIT]
            tout = [r for r in sel if r["bmag"] >= bc.B_LIMIT]
            kept = sum(1 for r in tin if bc.passes_bcut(r["phot_g_mean_mag"], r["bp_rp"]))
            let_in = sum(1 for r in tout if bc.passes_bcut(r["phot_g_mean_mag"], r["bp_rp"]))
            out("| %s | %s | %d of %d | %.0f%% | %d of %d |" % (
                label.replace("all, ", "").replace("all test stars", "all colours"), role, kept, len(tin), 100.0 * kept / max(1, len(tin)), let_in, len(tout)))
    rb = [r for r in allrows if r["role"] == "redbright"]
    out("\n## Bright red stars (G %s to %s), a check of the red end\n" % RED_BRIGHT_G)
    out("| BP-RP | n | B - G, smallest | B - G, median | method A bias (B) | method A std | APASS B < 13.5: kept by cut |")
    out("|---|---|---|---|---|---|---|")
    for lo, hi in RED_BRIGHT_BINS:
        sel = [r for r in rb if lo <= r["bp_rp"] < hi]
        if not sel:
            continue
        bg = sorted(r["bmag"] - r["phot_g_mean_mag"] for r in sel)
        d = [bc.b_mag_published(r["phot_g_mean_mag"], r["bp_rp"]) - r["bmag"] for r in sel]
        s2 = stats(d)
        tin = [r for r in sel if r["bmag"] < bc.B_LIMIT]
        kept = sum(1 for r in tin if bc.passes_bcut(r["phot_g_mean_mag"], r["bp_rp"]))
        out("| %.1f to %.1f | %d | %.2f | %.2f | %+.2f | %.2f | %d of %d |" % (
            lo, hi, len(sel), bg[0], bg[len(bg) // 2], s2["mean"], s2["std"], kept, len(tin)))
    # The margin for very red stars rests on the smallest B - G. Show it over every sample star that is
    # that red, from both sets, and from the main sample alone.
    very_red = [r for r in allrows if r["role"] in ("test", "train", "redbright") and r["bp_rp"] >= 2.5]
    main_red = [r for r in very_red if r["role"] in ("test", "train")]
    bg_all = sorted(r["bmag"] - r["phot_g_mean_mag"] for r in very_red)
    bg_main = sorted(r["bmag"] - r["phot_g_mean_mag"] for r in main_red)
    out("\nSmallest B - G over all %d sample stars with BP-RP 2.5 and above (main sample and bright red set): "
        "%.2f. Smallest in the main sample alone (%d stars): %.2f. This sets MIN_B_MINUS_G_VERY_RED in "
        "b_conversion.py." % (len(bg_all), bg_all[0], len(bg_main), bg_main[0]))
    with open(os.path.join(RESULTS, "b_validation.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "sample":
        fetch_sample()
    elif cmd == "fit":
        fit()
    elif cmd == "report":
        report()
    else:
        sys.exit(__doc__)
