"""Check, on DR3 stars, that reference_time, frequency and derived_primary_ecl_phase predict where the
primary eclipse falls in the star's own Gaia G light curve.

    python3 -I check_ephemeris.py

Stars: the 10 brightest long-period binaries in the DR3 stand-in list (data/full/eb_long_period.csv) that satisfy
rules fixed in advance (below), so that the choice is not made by eye. One DataLink request per star.

For each star the script computes the phase of every G measurement and the mean G inside and outside the
predicted primary eclipse window, and compares that window with 49 other windows of the same width, spread
round the phase circle. If the convention is right, the predicted window should be among the faintest.

  phase of a time t:      frac((t - reference_time) * frequency)
  primary eclipse centre: reference_time + (derived_primary_ecl_phase + n) / frequency, n = any whole number

As a control the same test is run with the sign of the phase reversed (a wrong convention). The same test at
the phase plus one half is shown too: that is where the secondary eclipse of a circular orbit falls, so a low
rank there is expected. The result goes to results/ephemeris_check.md. This tests the DR3 columns, which share their names
and, per the draft data model, their meaning with DR4. It does not test DR4 itself.
"""
import csv
import io
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
URL = "https://gea.esac.esa.int/data-server/data?ID=Gaia+DR3+%s&RETRIEVAL_TYPE=EPOCH_PHOTOMETRY&DATA_STRUCTURE=DATAMODEL_STANDARD&FORMAT=csv"
N_STARS = 10
N_WINDOWS = 50
TOP_RANK = 5   # "among the faintest": rank 5 or better out of 50 windows


def frac(x):
    return x - math.floor(x)


def wrap(d):
    """Signed distance on the circle of phase, in (-0.5, 0.5]."""
    d = frac(d)
    return d - 1.0 if d > 0.5 else d


def dimming(phases, mags, centre, width):
    """(mean G inside the window minus mean G outside, number of points inside)."""
    inside = [m for p, m in zip(phases, mags) if abs(wrap(p - centre)) < width / 2]
    outside = [m for p, m in zip(phases, mags) if abs(wrap(p - centre)) >= width / 2]
    if len(inside) < 1 or len(outside) < 3:
        return None, len(inside)
    return sum(inside) / len(inside) - sum(outside) / len(outside), len(inside)


def rank_of(phases, mags, centre, width):
    """Rank (1 is faintest) of the window at `centre` among N_WINDOWS windows round the circle."""
    d0, n0 = dimming(phases, mags, centre, width)
    if d0 is None:
        return None, None, n0
    others = []
    for k in range(N_WINDOWS):
        d, n = dimming(phases, mags, frac(centre + k / float(N_WINDOWS)), width)
        if d is not None:
            others.append(d)
    return 1 + sum(1 for d in others if d > d0 + 1e-12), d0, n0


def choose():
    rows = []
    with open(os.path.join(HERE, "data", "full", "eb_long_period.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                g = float(r["phot_g_mean_mag"])
                depth = float(r["derived_primary_ecl_depth"])
                dur = float(r["derived_primary_ecl_duration"])
                rank = float(r["global_ranking"])
            except ValueError:
                continue
            if r["model_type"].startswith("TWOGAUSSIANS") and 0.3 <= depth <= 3.0 and 0.05 <= dur <= 0.3 and rank > 0.4:
                rows.append((g, r))
    rows.sort(key=lambda x: x[0])
    return [r for g, r in rows[:N_STARS]]


def main():
    lines = ["# Does the DR3 ephemeris predict the eclipses in the star's own light curve?\n",
             "The %d brightest DR3 binaries with a period over 100 days, a TWOGAUSSIANS model, a primary depth of 0.3 to 3 mag, "
             "a primary duration of 0.05 to 0.3 of the period and global_ranking above 0.4 (rules fixed before looking). "
             "Rank 1 means the predicted window is the faintest of %d windows round the phase circle.\n" % (N_STARS, N_WINDOWS),
             "| source_id | G | period (d) | G points | in predicted window | dimming inside minus outside (mag) | table depth (mag) | rank, table phase | rank, reversed phase | rank, phase + 0.5 |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    good = {"table": 0, "minus": 0, "half": 0}
    ranks = {"table": [], "minus": []}
    wide = {"table": 0, "minus": 0}   # rank 11 or better: the faintest 20 per cent of windows
    used = 0
    for r in choose():
        sid = r["source_id"]
        text = common.fetch(URL % sid, kind="DataLink", note="epoch photometry for ephemeris check").decode()
        t, g = [], []
        for row in csv.DictReader(io.StringIO(text)):
            if row["g_transit_mag"] and row["rejected_by_photometry"] != "true":
                t.append(float(row["g_transit_time"]))
                g.append(float(row["g_transit_mag"]))
        f0, t0 = float(r["frequency"]), float(r["reference_time"])
        phi, width = float(r["derived_primary_ecl_phase"]), float(r["derived_primary_ecl_duration"])
        phases = [frac((ti - t0) * f0) for ti in t]
        rk, d0, n0 = rank_of(phases, g, phi, width)
        rk_m, _, _ = rank_of(phases, g, frac(-phi), width)
        rk_h, _, _ = rank_of(phases, g, frac(phi + 0.5), width)
        if rk is None:
            lines.append("| %s | %.2f | %.1f | %d | %d | n/a | %.2f | n/a | n/a | n/a |" % (
                sid, float(r["phot_g_mean_mag"]), 1 / f0, len(t), n0, float(r["derived_primary_ecl_depth"])))
            continue
        used += 1
        good["table"] += rk <= TOP_RANK
        good["minus"] += (rk_m or 99) <= TOP_RANK
        good["half"] += (rk_h or 99) <= TOP_RANK
        ranks["table"].append(rk)
        wide["table"] += rk <= 11
        if rk_m is not None:
            ranks["minus"].append(rk_m)
            wide["minus"] += rk_m <= 11
        lines.append("| %s | %.2f | %.1f | %d | %d | %+.2f | %.2f | %d | %s | %s |" % (
            sid, float(r["phot_g_mean_mag"]), 1 / f0, len(t), n0, d0, float(r["derived_primary_ecl_depth"]), rk,
            rk_m, rk_h))
    lines.append("")
    med = lambda v: sorted(v)[len(v) // 2] if v else None
    lines.append("Predicted window among the %d faintest of %d: **%d of %d stars** with the table's phase, %d with the sign of the "
                 "phase reversed, %d at phase plus 0.5. Among the 11 faintest (20 per cent): %d with the table's phase, %d with "
                 "the sign reversed. Median rank: %s with the table's phase, %s reversed. Chance alone gives %.1f stars in the "
                 "top %d, %.1f in the top 11, and a median rank near 25." % (
                     TOP_RANK, N_WINDOWS, good["table"], used, good["minus"], good["half"], wide["table"], wide["minus"],
                     med(ranks["table"]), med(ranks["minus"]), used * TOP_RANK / float(N_WINDOWS), TOP_RANK, used * 0.22))
    lines.append("")
    lines.append("Each window holds only a few points, because Gaia observes a given star about once every 20 to 30 days on "
                 "average, and in several stars the dimming rests on one or two visits. This is a weak test of the phase "
                 "convention. It says nothing about whether the period is right to a fraction of a cycle over 100 years.")
    with open(os.path.join(HERE, "results", "ephemeris_check.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
