"""Write results/dr3_checks.md: what the DR3 stand-in queries returned, in plain tables.

    python3 -I analyze_dr3.py

Reads results/run_log.tsv, results/out/*.csv and data/full/*.csv (written by run_dr3_checks.py).
Makes no network request.
"""
import csv
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results", "out")
FULL = os.path.join(HERE, "data", "full")
REPORT = os.path.join(HERE, "results", "dr3_checks.md")

# Harvard plates: 1890 to 1989 (DASCH). Days from the DR3 mid-time (about JD 2457400) back to the plate years.
JD_2016 = 2457388.5
JD_1890, JD_1950, JD_1989 = 2411368.5, 2433282.5, 2447527.5


def read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t" if path.endswith(".tsv") else ","))


def num(x):
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def pct(sorted_vals, q):
    if not sorted_vals:
        return float("nan")
    i = min(len(sorted_vals) - 1, max(0, int(round(q * (len(sorted_vals) - 1)))))
    return sorted_vals[i]


def table(out, header, rows):
    out.append("| " + " | ".join(header) + " |")
    out.append("|" + "|".join("---" for _ in header) + "|")
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    out.append("")


def last_ok(log, name, variant="full"):
    hit = [r for r in log if r["query"] == name and r["variant"] == variant and r["status"] == "ok"]
    return hit[-1] if hit else None


def main():
    out = []
    w = out.append
    log = read(os.path.join(HERE, "results", "run_log.tsv"))
    w("# What the DR3 stand-in queries returned\n")
    w("Run on the live Gaia archive (anonymous, synchronous queries). Dates are in `run_log.tsv`. "
      "The full row lists are in `data/full/` and are not committed; the first 20 rows of each are in `out/`.\n")

    w("## Row counts\n")
    rows = []
    for name in sorted({r["query"] for r in log if not r["query"].startswith("sanity")}):
        r = last_ok(log, name)
        if r:
            rows.append([name, r["n_rows"], r["value"], r["utc_time"][:10]])
    table(out, ["query", "rows returned", "count value", "date"], rows)

    # sanity checks
    w("## Checks on the stand-in tables\n")
    ref = read(os.path.join(OUT, "sanity_eb_reference_time_range.csv"))[0]
    w("- `vari_eclipsing_binary.reference_time` ranges from %.1f to %.1f. Gaia DR3 covers 25 Jul 2014 to 28 May 2017, "
      "which is 1666 to 2704 on the scale BJD(TCB) minus 2455197.5. The values fit that scale, which supports the zero point "
      "the DR4 data model states." % (float(ref["min_reference_time"]), float(ref["max_reference_time"])))
    w("- `frequency` ranges from %.5f to %.2f per day, so periods run from %.2f to %.0f days.\n" % (
        float(ref["min_frequency"]), float(ref["max_frequency"]), 1 / float(ref["max_frequency"]), 1 / float(ref["min_frequency"])))
    pt = read(os.path.join(OUT, "sanity_pt_reference_time_range.csv"))[0]
    w("- `vari_planetary_transit.transit_reference_time` ranges from %.1f to %.1f (same scale, inside the DR3 span). "
      "`transit_period` ranges from %.2f to %.1f days." % (
          float(pt["min_t0"]), float(pt["max_t0"]), float(pt["min_period"]), float(pt["max_period"])))
    cp = read(os.path.join(OUT, "sanity_pt_copies_differ.csv"))[0]
    w("- `vari_planetary_transit` and `vari_planetary_transit_13june2022` both have 214 rows. Joined on source_id, "
      "%s rows differ in period or reference time, so the second table is a different solution of the same stars. "
      "The stand-in uses the table without a date in its name.\n" % cp["n_rows_that_differ"])

    w("## Eclipsing binaries by period (all DR3 rows)\n")
    rows = []
    total = 0
    for r in read(os.path.join(OUT, "eb_summary_period.csv")):
        lo = float(r["log_period_bin"])
        n = int(r["n_sources"])
        total += n
        rows.append(["%.4g to %.4g" % (10 ** lo, 10 ** (lo + 0.25)), "%.2f" % lo, n])
    table(out, ["period range (days)", "log10 period, lower edge", "stars"], rows)
    w("Total %d. The bin edges are quarter-decades of log10(period), so the bins are not round numbers of days.\n" % total)

    eb = read(os.path.join(FULL, "eb_long_period.csv"))
    n = len(eb)
    w("## Long-period eclipsing binaries (period over 100 days): %d stars\n" % n)

    periods = sorted(float(r["period_days"]) for r in eb)
    w("Period: median %.0f d, 90th percentile %.0f d, longest %.0f d. Stars over 200 d: %d. Over 400 d: %d.\n" % (
        pct(periods, 0.5), pct(periods, 0.9), periods[-1], sum(p > 200 for p in periods), sum(p > 400 for p in periods)))

    mt = {}
    for r in read(os.path.join(OUT, "eb_summary_long_period_model_type.csv")):
        mt[r["model_type"]] = int(r["n_sources"])
    w("Model types: " + ", ".join("%s %d" % kv for kv in sorted(mt.items())) + ".\n")

    w("### Magnitude of G (mean, from gaia_source)\n")
    rows = []
    for r in read(os.path.join(OUT, "eb_summary_long_period_gmag.csv")):
        b = r["g_bin"]
        rows.append(["no G" if b == "" else "%d to %d" % (float(b), float(b) + 1), r["n_sources"]])
    table(out, ["G", "stars"], rows)
    gs = sorted(g for g in (num(r["phot_g_mean_mag"]) for r in eb) if g is not None)
    w("Brighter than G = 13.5: %d stars. Brighter than G = 12: %d. Brightest G: %.2f.\n" % (
        sum(g < 13.5 for g in gs), sum(g < 12 for g in gs), gs[0]))

    w("### Estimated B (published chain, README.md)\n")
    rows = []
    for r in read(os.path.join(OUT, "eb_summary_long_period_bmag.csv")):
        b = r["b_bin"]
        rows.append(["no BP-RP" if b == "" else "%d to %d" % (float(b), float(b) + 1), r["n_sources"]])
    table(out, ["estimated B", "stars"], rows)

    cut = read(os.path.join(FULL, "eb_long_period_bcut.csv"))
    w("Stars that pass the B cut (ADQL in `eb_long_period_bcut.adql`): **%d**. The count query "
      "`eb_count_long_period_bcut` gave %s." % (len(cut), last_ok(log, "eb_count_long_period_bcut")["value"]))
    cols = [num(r["bp_rp"]) for r in cut]
    w("Of them, BP-RP below 2.0: %d. From 2.0 to 2.5: %d. 2.5 and above: %d. No BP-RP: %d.\n" % (
        sum(1 for c in cols if c is not None and c < 2.0), sum(1 for c in cols if c is not None and 2.0 <= c < 2.5),
        sum(1 for c in cols if c is not None and c >= 2.5), sum(1 for c in cols if c is None)))

    w("### Eclipse depth and model type among the stars that pass the B cut\n")
    deep = sum(1 for r in cut if (num(r["derived_primary_ecl_depth"]) or 0) >= 0.3)
    deeper = sum(1 for r in cut if (num(r["derived_primary_ecl_depth"]) or 0) >= 0.5)
    nogauss = sum(1 for r in cut if num(r["derived_primary_ecl_phase"]) is None)
    w("Primary eclipse at least 0.3 mag deep (G): %d of %d. At least 0.5 mag: %d. No eclipse phase (NaN): %d. "
      "Harvard plates only show eclipses deeper than about 0.3 to 0.5 mag (astronomy report in `notes/reports/`).\n" % (
          deep, len(cut), deeper, nogauss))
    mt2 = {}
    for r in cut:
        mt2[r["model_type"]] = mt2.get(r["model_type"], 0) + 1
    w("Model types among them: " + ", ".join("%s %d" % kv for kv in sorted(mt2.items())) + ".\n")

    w("### Can an eclipse time be carried back to the Harvard plates?\n")
    w("The error on the phase of an eclipse after dt days is about dt times `frequency_error`, in cycles. "
      "From the DR3 reference time (about 2016) back to 1950 is about %d days, back to 1890 about %d days. "
      "This uses the formal error only. It ignores aliasing, which makes it a lower bound." % (
          JD_2016 - JD_1950, JD_2016 - JD_1890))
    w("A phase error well below 0.1 cycle is needed to say where an eclipse fell.\n")
    rows = []
    for label, jd in [("1989", JD_1989), ("1950", JD_1950), ("1890", JD_1890)]:
        dt = JD_2016 - jd
        allv = sorted(float(r["frequency_error"]) * dt for r in eb if num(r["frequency_error"]) is not None)
        cutv = sorted(float(r["frequency_error"]) * dt for r in cut if num(r["frequency_error"]) is not None)
        rows.append([label, int(dt), "%.2f" % pct(allv, 0.5), sum(v < 0.1 for v in allv), len(allv),
                     "%.2f" % pct(cutv, 0.5), sum(v < 0.1 for v in cutv), len(cutv)])
    table(out, ["year", "days back", "median phase error, all (cycles)", "all with error < 0.1", "of",
                "median, B-cut stars", "B-cut with error < 0.1", "of"], rows)

    w("### Mean G against the model's out-of-eclipse level\n")
    d = sorted(x for x in (None if num(r["phot_g_mean_mag"]) is None or num(r["geom_model_reference_level"]) is None
                           else num(r["phot_g_mean_mag"]) - num(r["geom_model_reference_level"]) for r in eb) if x is not None)
    w("`phot_g_mean_mag` minus `geom_model_reference_level`, %d stars: 5th percentile %+.3f, median %+.3f, 95th percentile %+.3f mag. "
      "A positive value means the mean is fainter than the out-of-eclipse level. "
      "Cut margins in README.md are larger than this.\n" % (len(d), pct(d, 0.05), pct(d, 0.5), pct(d, 0.95)))

    w("## Planetary-transit table\n")
    rows = []
    for r in read(os.path.join(OUT, "pt_summary_period.csv")):
        lo = float(r["log_period_bin"])
        rows.append(["%.1f to %.1f" % (10 ** lo, 10 ** (lo + 0.25)), r["n_candidates"], "%.1f" % float(r["mean_depth_mmag"]),
                     "%.3f" % float(r["mean_duration_days"]), r["min_in_transit"], r["max_in_transit"]])
    table(out, ["period (days)", "candidates", "mean depth (mmag)", "mean duration (d)", "fewest in-transit obs", "most"], rows)
    ptf = read(os.path.join(FULL, "pt_candidates.csv"))
    w("Candidates: %d. With a gaia_source row: %d. The neighbourhood stand-in (DR3 to DR2 IDs) returned %d rows for %d "
      "distinct candidates.\n" % (len(ptf), sum(1 for r in ptf if r["ra"] != ""), len(read(os.path.join(FULL, "pt_candidates_neighbours.csv"))),
                                  len({r["source_id"] for r in read(os.path.join(FULL, "pt_candidates_neighbours.csv"))})))
    w("There is no TESS cross-match table in the Gaia archive for DR3 (checked in `TAP_SCHEMA.tables` on 27 Oct 2026) and "
      "none in the draft DR4 data model (searched for TESS, TIC).\n")

    w("## Cone search stand-in (`flags_in_cone`)\n")
    rows = read(os.path.join(OUT, "flags_in_cone.csv"))
    w("Circle of 0.0175 degrees (63 arcseconds, 3 TESS pixels) around the first long-period binary: %d rows. "
      "The target has eb_frequency %s and flag %s.\n" % (len(rows), rows[0]["eb_frequency"][:8], rows[0]["phot_variable_flag"]))

    w("## First rows\n")
    w("`out/eb_long_period_top20.csv`, `out/pt_candidates_top20.csv` and the other files in `out/` hold the first rows of each query.\n")
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    sys.exit(main())
