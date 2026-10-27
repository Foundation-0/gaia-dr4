"""Write the query files: dr4/*.adql (DR4 names) and dr3/*.adql (DR3 stand-ins).

Run:  python3 -I build_queries.py

The DR4 text is the single source. The DR3 text is made from it by make_standin.convert, so the two
cannot drift apart. The B-magnitude formulas come from b_conversion.py for the same reason.
test_queries.py checks that the committed files equal what this script writes.

The header of each file says which question it serves, which DR3 tables stood in, which DR4 columns it
relies on, and when the DR3 stand-in last ran without error. That date and the row count are read
from results/run_log.tsv, which run_dr3_checks.py writes. Run the checks, then run this script again.
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import b_conversion as bc  # noqa: E402
import make_standin as ms  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RUN_LOG = os.path.join(HERE, "results", "run_log.tsv")

B_V = bc.adql_v()
B_BV = bc.adql_bv_published()
B_B = bc.adql_b("published")
B_CUT = bc.adql_bcut()

EB_SELECT = """    eb.source_id,
    1.0 / eb.frequency AS period_days,
    eb.frequency,
    eb.frequency_error,
    eb.reference_time,
    eb.model_type,
    eb.global_ranking,
    eb.reduced_chi2,
    eb.geom_model_reference_level,
    eb.derived_primary_ecl_phase,
    eb.derived_primary_ecl_phase_error,
    eb.derived_primary_ecl_duration,
    eb.derived_primary_ecl_depth,
    eb.derived_secondary_ecl_phase,
    eb.derived_secondary_ecl_phase_error,
    eb.derived_secondary_ecl_duration,
    eb.derived_secondary_ecl_depth,
    eb.g_median,  -- DR4ONLY
    eb.g_num_obs,  -- DR4ONLY
    eb.sample_classification,  -- DR4ONLY
    eb.frequency_rv_consistency_flag,  -- DR4ONLY
    gs.ra,
    gs.dec,
    gs.ref_epoch,
    gs.pmra,
    gs.pmdec,
    gs.parallax,
    gs.parallax_error,
    gs.ruwe,
    gs.phot_g_mean_mag,
    gs.phot_bp_mean_mag,
    gs.phot_rp_mean_mag,
    gs.bp_rp,
    gs.phot_variable_flag,
    gs.teff,
    gs.g_photometry_origin,  -- DR4ONLY
    gs.colour_origin,  -- DR4ONLY
    {v} AS v_mag_estimate,
    {bv} AS b_minus_v_estimate,
    {b} AS b_mag_estimate,
    {b_ref} AS b_mag_estimate_out_of_eclipse""".format(v=B_V, bv=B_BV, b=B_B, b_ref=bc.adql_b("published", g="eb.geom_model_reference_level"))

EB_FROM = """FROM gaiadr4.vari_eclipsing_binary AS eb
LEFT OUTER JOIN gaiadr4.gaia_source AS gs
    ON gs.source_id = eb.source_id"""

PT_SELECT = """    pt.source_id,
    pt.transit_reference_time,
    pt.transit_period,
    pt.transit_duration,
    pt.transit_depth,
    pt.num_in_transit,
    gs.ra,
    gs.dec,
    gs.ref_epoch,
    gs.pmra,
    gs.pmdec,
    gs.parallax,
    gs.parallax_error,
    gs.ruwe,
    gs.phot_g_mean_mag,
    gs.phot_bp_mean_mag,
    gs.phot_rp_mean_mag,
    gs.bp_rp,
    gs.phot_variable_flag,
    gs.g_photometry_origin,  -- DR4ONLY
    gs.teff"""

PT_FROM = """FROM gaiadr4.vari_planetary_transit AS pt
LEFT OUTER JOIN gaiadr4.gaia_source AS gs
    ON gs.source_id = pt.source_id"""

# name -> dict(kind, question, body, note_untestable)
Q = {}


def add(name, kind, serves, body, untestable="", dr3_sample=None):
    Q[name] = {"kind": kind, "serves": serves, "body": body.strip() + "\n", "untestable": untestable}


add("eb_count_all", "count",
    "Check that the table has the row count ESA publishes (2,392,500 for DR4, 2,184,477 in DR3).",
    """SELECT COUNT(*) AS n_rows
FROM gaiadr4.vari_eclipsing_binary AS eb""",
    "The DR4 row count itself (2,392,500 per the Gaia DR4 page of 14 Sep 2026).")

add("eb_count_long_period", "count",
    "Question C. Number of eclipsing binaries with a period over 100 days (frequency below 0.01 per day).",
    """SELECT COUNT(*) AS n_long_period
FROM gaiadr4.vari_eclipsing_binary AS eb
WHERE eb.frequency < 0.01""",
    "The DR4 count. DR4 has 66 months of data, so more long periods are expected than in DR3.")

add("eb_count_long_period_bcut", "count",
    "Question C. Number of eclipsing binaries with a period over 100 days that pass the B < 13.5 cut "
    "(estimated from G, BP and RP, with margins; see README.md).",
    """SELECT COUNT(*) AS n_long_period_bcut
FROM gaiadr4.vari_eclipsing_binary AS eb
LEFT OUTER JOIN gaiadr4.gaia_source AS gs
    ON gs.source_id = eb.source_id
WHERE eb.frequency < 0.01
  AND {cut}""".format(cut=B_CUT),
    "Whether DR4 G magnitudes of eclipsing binaries (which may come from the EB model) behave like DR3 ones.")

add("eb_missing_from_gaia_source", "count",
    "Question C. Number of long-period eclipsing binaries that have no row in gaia_source. They would be lost by an inner "
    "join. Expected 0 in DR3. Limited to long periods because the same join over all 2.2 million rows ran past the "
    "archive's 60 second limit for synchronous queries.",
    """SELECT COUNT(*) AS n_long_period_eb_without_gaia_source_row
FROM gaiadr4.vari_eclipsing_binary AS eb
LEFT OUTER JOIN gaiadr4.gaia_source AS gs
    ON gs.source_id = eb.source_id
WHERE eb.frequency < 0.01
  AND gs.source_id IS NULL""",
    "The DR4 answer. DR4 gaia_source holds only sources with high-quality astrometry and photometry, so it may be above 0. "
    "Then position and magnitudes must come from all_source_astrometry and all_source_photometry, which DR3 does not have.")

add("eb_summary_period", "summary",
    "Question C. Number of eclipsing binaries per quarter-decade of period (log10 of the period in days, lower edge).",
    """SELECT
    t.log_period_bin,
    COUNT(*) AS n_sources
FROM (
    SELECT FLOOR(LOG10(1.0 / eb.frequency) * 4.0) / 4.0 AS log_period_bin
    FROM gaiadr4.vari_eclipsing_binary AS eb
    WHERE eb.frequency > 0.0
) AS t
GROUP BY t.log_period_bin
ORDER BY t.log_period_bin""",
    "The DR4 period distribution, in particular the longest periods DR4 reports (ESA states no maximum).")

add("eb_summary_long_period_model_type", "summary",
    "Question C. Number of long-period eclipsing binaries per model type. ELLIPSOIDAL models have no eclipse.",
    """SELECT
    eb.model_type,
    COUNT(*) AS n_sources
FROM gaiadr4.vari_eclipsing_binary AS eb
WHERE eb.frequency < 0.01
GROUP BY eb.model_type
ORDER BY eb.model_type""",
    "The DR4 model types and their counts.")

add("eb_summary_long_period_gmag", "summary",
    "Question C. Number of long-period eclipsing binaries per magnitude of G (lower edge of a 1 mag bin). "
    "The empty bin is stars with no G in gaia_source.",
    """SELECT
    t.g_bin,
    COUNT(*) AS n_sources
FROM (
    SELECT FLOOR(gs.phot_g_mean_mag) AS g_bin
    FROM gaiadr4.vari_eclipsing_binary AS eb
    LEFT OUTER JOIN gaiadr4.gaia_source AS gs
        ON gs.source_id = eb.source_id
    WHERE eb.frequency < 0.01
) AS t
GROUP BY t.g_bin
ORDER BY t.g_bin""",
    "The DR4 magnitude distribution.")

add("eb_summary_long_period_bmag", "summary",
    "Question C. Number of long-period eclipsing binaries per estimated B magnitude (published chain, lower edge of a "
    "1 mag bin). The estimate fails for BP-RP above 2.5 (README.md). The empty bin is stars with no BP-RP.",
    """SELECT
    t.b_bin,
    COUNT(*) AS n_sources
FROM (
    SELECT FLOOR({b}) AS b_bin
    FROM gaiadr4.vari_eclipsing_binary AS eb
    LEFT OUTER JOIN gaiadr4.gaia_source AS gs
        ON gs.source_id = eb.source_id
    WHERE eb.frequency < 0.01
) AS t
GROUP BY t.b_bin
ORDER BY t.b_bin""".format(b=B_B),
    "The DR4 distribution of the B estimate.")

add("eb_long_period", "rows",
    "Question C. Eclipsing binaries with a period over 100 days, with what is needed to predict eclipse times "
    "(reference_time, frequency, eclipse phases, durations) and gaia_source position, parallax, magnitudes and colour. "
    "No magnitude cut. V and B are estimated from G, BP and RP (README.md).",
    """SELECT
{select}
{frm}
WHERE eb.frequency < 0.01
ORDER BY eb.source_id""".format(select=EB_SELECT, frm=EB_FROM),
    "Everything about DR4 values: how many rows, which model types and periods, whether eclipse phases follow the "
    "convention in README.md for DR4, whether DR4 G for eclipsing binaries is a mean or an out-of-eclipse value.")

add("eb_long_period_bcut", "rows",
    "Question C. The same as eb_long_period, with the cut 'brighter than about B = 13.5' written in ADQL from G, BP and RP. "
    "The cut keeps every star that might pass (margins in README.md), so some stars up to 0.25 mag fainter get through "
    "(0.5 mag for BP-RP from 2.0 to 2.5). Rows with BP-RP above 2.5 are cut by G alone.",
    """SELECT
{select}
{frm}
WHERE eb.frequency < 0.01
  AND {cut}
ORDER BY eb.source_id""".format(select=EB_SELECT, frm=EB_FROM, cut=B_CUT),
    "The DR4 row count and the B cut on DR4 magnitudes. The margins come from DR3 magnitudes.")

add("eb_by_source_ids", "template",
    "Questions A and B support. The same columns as eb_long_period for a list of source IDs, with no period cut. "
    "Replace @SOURCE_IDS@ with a comma-separated list of DR4 source IDs. DR4 IDs differ from DR3 IDs: map them "
    "through dr3_neighbourhood first.",
    """SELECT
{select}
{frm}
WHERE eb.source_id IN (@SOURCE_IDS@)
ORDER BY eb.source_id""".format(select=EB_SELECT, frm=EB_FROM),
    "Whether the DR3-to-DR4 ID mapping finds the same stars.")

add("pt_count_all", "count",
    "Check that the table has the row count ESA publishes (1,007 for DR4; 214 in DR3).",
    """SELECT COUNT(*) AS n_rows
FROM gaiadr4.vari_planetary_transit AS pt""",
    "The DR4 row count.")

add("pt_summary_period", "summary",
    "Transit candidates per quarter-decade of period (log10 of the period in days, lower edge), with mean depth and "
    "duration and the range of the number of in-transit observations.",
    """SELECT
    t.log_period_bin,
    COUNT(*) AS n_candidates,
    AVG(t.depth_mmag) AS mean_depth_mmag,
    AVG(t.duration_days) AS mean_duration_days,
    MIN(t.n_in_transit) AS min_in_transit,
    MAX(t.n_in_transit) AS max_in_transit
FROM (
    SELECT
        FLOOR(LOG10(pt.transit_period) * 4.0) / 4.0 AS log_period_bin,
        pt.transit_depth AS depth_mmag,
        pt.transit_duration AS duration_days,
        pt.num_in_transit AS n_in_transit
    FROM gaiadr4.vari_planetary_transit AS pt
    WHERE pt.transit_period > 0.0
) AS t
GROUP BY t.log_period_bin
ORDER BY t.log_period_bin""",
    "The DR4 distribution (1,007 rows).")

add("pt_candidates", "rows",
    "Planetary-transit candidates with what is needed to predict transit times (transit_reference_time, transit_period, "
    "transit_duration, transit_depth) and gaia_source position, parallax, magnitudes and colour. No TESS cross-match table "
    "exists in the archive: see pt_candidates_neighbours for the link to older Gaia IDs.",
    """SELECT
{select}
{frm}
ORDER BY pt.source_id""".format(select=PT_SELECT, frm=PT_FROM),
    "All DR4 values.")

add("pt_candidates_neighbours", "rows",
    "Planetary-transit candidates with the neighbourhood table that links IDs between releases. In DR4 it links to DR3 IDs "
    "(dr3_neighbourhood). The DR3 stand-in links to DR2 IDs (dr2_neighbourhood), which is the ID the TESS Input Catalog uses. "
    "A candidate can have several rows. A candidate with no row is left out, because a LEFT JOIN to these billion-row "
    "tables ran past the archive's 60 second limit: compare the number of distinct source_id returned with the count.",
    """SELECT
    pt.source_id,
    pt.transit_reference_time,
    pt.transit_period,
    pt.transit_duration,
    pt.transit_depth,
    gs.ra,
    gs.dec,
    gs.phot_g_mean_mag,
    nb.source_id AS neighbourhood_source_id,
    nb.dr3_source_id AS neighbourhood_older_source_id,
    nb.probable_match,  -- DR4ONLY
    nb.angular_distance,
    nb.magnitude_difference
FROM gaiadr4.vari_planetary_transit AS pt
LEFT OUTER JOIN gaiadr4.gaia_source AS gs
    ON gs.source_id = pt.source_id
JOIN gaiadr4.dr3_neighbourhood AS nb
    ON nb.source_id = pt.source_id
ORDER BY pt.source_id, nb.angular_distance""",
    "All of it: dr3_neighbourhood exists only in DR4. The stand-in tests the join pattern with the DR3-to-DR2 table. "
    "The step from the DR3 ID to a TIC number is the job of the tic-to-gaia task.")

add("pt_by_source_ids", "template",
    "Questions A and B support. The same columns as pt_candidates for a list of source IDs. "
    "Replace @SOURCE_IDS@ with a comma-separated list of DR4 source IDs.",
    """SELECT
{select}
{frm}
WHERE pt.source_id IN (@SOURCE_IDS@)
ORDER BY pt.source_id""".format(select=PT_SELECT, frm=PT_FROM),
    "Whether the DR3-to-DR4 ID mapping finds the same stars.")

add("flags_in_cone", "template",
    "Question B support. Every Gaia source in a circle with its variability flag, and its eclipsing-binary and "
    "planetary-transit rows if it has them. Replace @RA@ and @DEC@ (degrees, ICRS) and @RADIUS_DEG@ (degrees). "
    "The run used 0.0175 degrees (63 arcseconds, three TESS pixels of 21 arcseconds each). A real TESS aperture "
    "is not a circle of that size and needs its own radius.",
    """SELECT
    gs.source_id,
    gs.ra,
    gs.dec,
    gs.phot_g_mean_mag,
    gs.bp_rp,
    gs.phot_variable_flag,
    gs.g_photometry_origin,  -- DR4ONLY
    eb.frequency AS eb_frequency,
    eb.model_type AS eb_model_type,
    eb.derived_primary_ecl_depth AS eb_primary_depth,
    pt.transit_period,
    pt.transit_depth
FROM gaiadr4.gaia_source AS gs
LEFT OUTER JOIN gaiadr4.vari_eclipsing_binary AS eb
    ON eb.source_id = gs.source_id
LEFT OUTER JOIN gaiadr4.vari_planetary_transit AS pt
    ON pt.source_id = gs.source_id
WHERE 1 = CONTAINS(POINT('ICRS', gs.ra, gs.dec), CIRCLE('ICRS', @RA@, @DEC@, @RADIUS_DEG@))
ORDER BY gs.phot_g_mean_mag""",
    "The DR4 flags. DR4 also lists in_vari_eclipsing_binary and in_vari_planetary_transit in vari_summary (draft), "
    "not used here.")


# Queries that exist only for DR4. DR3 has no tables to stand in for them, so they are not tested on DR3.
Q4ONLY = {}

Q4ONLY["eb_long_period_all_source"] = {
    "kind": "dr4only",
    "serves": "Question C, fallback. The same as eb_long_period_bcut, but position and magnitudes come from all_source_astrometry "
              "and all_source_photometry, which cover nearly every source, instead of gaia_source, which holds only sources "
              "with high-quality astrometry and photometry. Use it if eb_missing_from_gaia_source is above 0.",
    "body": """SELECT
    eb.source_id,
    1.0 / eb.frequency AS period_days,
    eb.frequency,
    eb.frequency_error,
    eb.reference_time,
    eb.model_type,
    eb.derived_primary_ecl_phase,
    eb.derived_primary_ecl_duration,
    eb.derived_primary_ecl_depth,
    eb.derived_secondary_ecl_phase,
    eb.derived_secondary_ecl_duration,
    eb.derived_secondary_ecl_depth,
    ast.in_gaia_source,
    ast.ra,
    ast.dec,
    ast.ref_epoch,
    ast.pmra,
    ast.pmdec,
    ast.parallax,
    ast.parallax_error,
    ast.ruwe,
    ph.phot_g_mean_mag,
    ph.phot_bp_mean_mag,
    ph.phot_rp_mean_mag,
    ph.bp_rp,
    {b} AS b_mag_estimate
FROM gaiadr4.vari_eclipsing_binary AS eb
LEFT OUTER JOIN gaiadr4.all_source_astrometry AS ast
    ON ast.source_id = eb.source_id
LEFT OUTER JOIN gaiadr4.all_source_photometry AS ph
    ON ph.source_id = eb.source_id
WHERE eb.frequency < 0.01
  AND {cut}
ORDER BY eb.source_id""".format(b=bc.adql_b("published", g="ph.phot_g_mean_mag", c="ph.bp_rp"),
                                cut=bc.adql_bcut(g="ph.phot_g_mean_mag", c="ph.bp_rp")) + "\n",
    "untestable": "All of it. DR3 has no all_source_astrometry or all_source_photometry. Table and column names are only checked "
                  "against the draft data model.",
}


def read_run_log():
    """query name -> (date, n_rows) of the last successful run of the DR3 stand-in."""
    out = {}
    if not os.path.exists(RUN_LOG):
        return out
    with open(RUN_LOG, encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            if r["status"] == "ok" and r["variant"] == "full":
                out[r["query"]] = (r["utc_time"][:10], r["n_rows"])
    return out


def relied_on(body):
    """Return {dr4 table: sorted columns} read from the query text."""
    tables, _ = ms.load_map()
    aliases = ms.aliases_of(body, tables)
    found = {}
    for line in body.split("\n"):
        code = line.split("--", 1)[0]
        for t, c in ms.columns_used(code, aliases):
            found.setdefault(t, set()).add(c)
    return {t: sorted(c) for t, c in found.items()}


WRAP_WIDTH = 118
WRAP_PREFIX = "--   "


def wrap(lines):
    """Break comment lines longer than WRAP_WIDTH. Breaks at the last space that comes after the
    prefix of a continuation line. A word with no such space is cut at WRAP_WIDTH, so the loop always
    gets shorter and cannot hang."""
    out = []
    for text in lines:
        while len(text) > WRAP_WIDTH:
            cut = text.rfind(" ", len(WRAP_PREFIX), WRAP_WIDTH)
            if cut < 0:
                out.append(text[:WRAP_WIDTH])
                text = WRAP_PREFIX + text[WRAP_WIDTH:]
            else:
                out.append(text[:cut])
                text = WRAP_PREFIX + text[cut + 1:]
        out.append(text)
    return out


def header4(name, q, log):
    cols = relied_on(q["body"])
    dr3_tables = sorted({ms.load_map()[0][t] for t in cols if t in ms.load_map()[0]})
    ran = log.get(name)
    if q["kind"] == "dr4only":
        lines = ["-- Query: %s (DR4 names, no DR3 stand-in)" % name,
                 "-- Serves: %s" % q["serves"],
                 "-- Names: the draft DR4 data model of 26 Jun 2026. The schema name gaiadr4 is taken from that model's own example query.",
                 "-- DR3 stand-in: none. DR3 has no all_source_astrometry or all_source_photometry.",
                 "-- Last ran on DR3: never, for that reason. Last ran on DR4: never. The archive has no DR4 until 2 Dec 2026.",
                 "-- DR4 columns this query relies on:"]
        for t in sorted(cols):
            lines.append("--   %s: %s" % (t, ", ".join(cols[t])))
        lines.append("-- Cannot be tested before release: %s" % q["untestable"])
        return "\n".join(wrap(lines)) + "\n"
    lines = ["-- Query: %s (DR4 names)" % name,
             "-- Serves: %s" % q["serves"],
             "-- Names: the draft DR4 data model of 26 Jun 2026. The schema name gaiadr4 is taken from that model's own example query.",
             "-- DR3 stand-in: dr3/%s.adql, made from this file by make_standin.py. DR3 tables: %s." % (name, ", ".join(dr3_tables)),
             ("-- Last ran without error on the DR3 stand-in: %s (%s rows; results/run_log.tsv)." % ran) if ran
             else "-- Last ran without error on the DR3 stand-in: not yet run.",
             "-- Last ran on DR4: never. The archive has no DR4 until 2 Dec 2026.",
             "-- DR4 columns this query relies on:"]
    for t in sorted(cols):
        lines.append("--   %s: %s" % (t, ", ".join(cols[t])))
    lines.append("-- Lines tagged DR4ONLY have no DR3 equivalent and are dropped from the stand-in.")
    if q["kind"] == "template":
        lines.append("-- This is a template: replace the @...@ words before running it.")
    lines.append("-- Cannot be tested before release: %s" % q["untestable"])
    return "\n".join(wrap(lines)) + "\n"


def header3(name, q, log):
    ran = log.get(name)
    cols = relied_on(q["body"])
    tables, _ = ms.load_map()
    lines = ["-- Query: %s (DR3 stand-in)" % name,
             "-- Serves: %s" % q["serves"],
             "-- Made from dr4/%s.adql by make_standin.py using column_map.tsv. Do not edit by hand." % name,
             "-- DR3 tables used: %s." % ", ".join(sorted({tables[t] for t in cols})),
             ("-- Last ran without error: %s, %s rows (results/run_log.tsv)." % ran) if ran
             else "-- Last ran without error: not yet run."]
    if q["kind"] == "template":
        lines.append("-- This is a template: replace the @...@ words before running it.")
    return "\n".join(wrap(lines)) + "\n"


def build(write=True):
    log = read_run_log()
    files = {}
    for name, q in Q.items():
        body4 = q["body"]
        body3 = ms.convert(body4)
        files[os.path.join("dr4", name + ".adql")] = header4(name, q, log) + body4
        files[os.path.join("dr3", name + ".adql")] = header3(name, q, log) + body3
    for name, q in Q4ONLY.items():
        files[os.path.join("dr4_only", name + ".adql")] = header4(name, q, log) + q["body"]
    if write:
        for d in ("dr4", "dr3", "dr4_only"):
            os.makedirs(os.path.join(HERE, d), exist_ok=True)
        for rel, text in files.items():
            with open(os.path.join(HERE, rel), "w", encoding="utf-8") as f:
                f.write(text)
        print("wrote %d files" % len(files))
    return files


if __name__ == "__main__":
    build()
