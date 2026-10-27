"""Build column_map.tsv: the DR4 draft names, the DR3 stand-in names, units and mismatches.

Inputs
  datamodel/dr4_draft_columns.tsv   from datamodel_columns.py (draft DR4 data model, 26 Jun 2026)
  results/dr3_tap_schema_columns.csv  the live Gaia archive's TAP_SCHEMA, fetched on 27 Oct 2026

Run:  python3 -I build_column_map.py

Each line of column_map.tsv is one table or one column.
  kind        table or column
  dr4_table   table name in DR4 (for kind=table with the schema, e.g. gaiadr4.gaia_source)
  dr4_name    column name in the draft DR4 data model ("-" if none)
  dr3_table   table that stands in for it in DR3
  dr3_name    column name in DR3 ("-" if none)
  dr4_unit, dr3_unit, dr4_type, dr3_type
  status      same | renamed | dr4_only | dr3_only
  unit_check  same | text_differs | zero_point | n/a
  notes       what differs and why it matters

make_standin.py reads this file. A column with status dr4_only has no DR3 equivalent.
"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DR4_FILE = os.path.join(HERE, "datamodel", "dr4_draft_columns.tsv")
DR3_FILE = os.path.join(HERE, "results", "dr3_tap_schema_columns.csv")
OUT = os.path.join(HERE, "column_map.tsv")

SCHEMA4, SCHEMA3 = "gaiadr4", "gaiadr3"

# (dr4 table, dr3 table). The DR4 schema name comes from the draft data model's own example query
# ("from gaiadr4.gaia_source"). It is not yet confirmed by a live archive.
TABLES = [
    ("vari_eclipsing_binary", "vari_eclipsing_binary"),
    ("vari_planetary_transit", "vari_planetary_transit"),
    ("gaia_source", "gaia_source"),
    ("dr3_neighbourhood", "dr2_neighbourhood"),
]

TABLE_NOTES = {
    "vari_eclipsing_binary": "DR4 draft: 66 months of data. DR3: 34 months.",
    "vari_planetary_transit": "DR3 has two copies, vari_planetary_transit and vari_planetary_transit_13june2022 (214 rows each).",
    "gaia_source": "DR4 gaia_source only holds sources with both high-quality astrometry and photometry "
                   "(Gaia DR4 page, 14 Sep 2026). In DR3 every variable star is in gaia_source. In DR4 an "
                   "eclipsing binary can be missing from it: use a LEFT JOIN and check all_source_astrometry "
                   "and all_source_photometry.",
    "dr3_neighbourhood": "Stand-in for one step of the ID chain. DR4 dr3_neighbourhood links DR4 to DR3 IDs. "
                         "DR3 dr2_neighbourhood links DR3 to DR2 IDs. The TESS Input Catalog uses DR2 IDs.",
}

# Curated mismatches. Key: (dr4 table, dr4 column).
NOTES = {
    ("vari_eclipsing_binary", "reference_time"): "Days, BJD in TCB minus 2455197.5. DR3 TAP_SCHEMA gives only 'd'; "
        "the DR3 values fall inside the DR3 time span on that scale (results/dr3_checks.md).",
    ("vari_eclipsing_binary", "frequency"): "Per day. Period in days = 1 / frequency. Period > 100 d is frequency < 0.01. "
        "The table has no period column.",
    ("vari_eclipsing_binary", "frequency_error"): "Per day. Error on the period grows with the time since reference_time: "
        "phase error after dt days is about dt * frequency_error cycles.",
    ("vari_eclipsing_binary", "model_type"): "DR4 draft values: ONEGAUSSIAN, ONEGAUSSIAN_WITH_ELLIPSOIDAL, TWOGAUSSIANS, "
        "TWOGAUSSIANS_WITH_ELLIPSOIDAL_ON_ECLIPSE1, TWOGAUSSIANS_WITH_ELLIPSOIDAL_ON_ECLIPSE2, ELLIPSOIDAL. "
        "ELLIPSOIDAL has no eclipse. DR3 values are listed in results/dr3_checks.md.",
    ("vari_eclipsing_binary", "derived_primary_ecl_phase"): "Phase relative to reference_time. DR3 values lie between 0 and 1. Empty when the model has no "
        "Gaussian (the 82 long-period ELLIPSOIDAL stars in DR3). The DR4 draft says NaN.",
    ("vari_eclipsing_binary", "derived_secondary_ecl_phase"): "Phase relative to reference_time. Empty (NaN in the DR4 draft) when there is no second Gaussian.",
    ("vari_eclipsing_binary", "derived_primary_ecl_duration"): "A fraction of the period, not days. Days = duration * period.",
    ("vari_eclipsing_binary", "derived_secondary_ecl_duration"): "A fraction of the period, not days.",
    ("vari_eclipsing_binary", "derived_primary_ecl_depth"): "Magnitudes in G.",
    ("vari_eclipsing_binary", "geom_model_reference_level"): "G magnitude outside eclipse, from the model.",
    ("vari_eclipsing_binary", "num_model_parameters"): "Integer type is narrower in DR4 (byte); no effect on queries.",
    ("vari_eclipsing_binary", "g_median"): "DR4 only. Median G of the input light curve. Useful next to gaia_source.phot_g_mean_mag.",
    ("vari_eclipsing_binary", "sample_classification"): "DR4 only. String class from Mowlavi et al. (2023) Table A.1, per the data model.",
    ("vari_eclipsing_binary", "frequency_rv_consistency_flag"): "DR4 only. Compares the model frequency with the radial-velocity "
        "period. 3 means the RV frequency is half the model frequency, 2 means double, 1 consistent, 0 inconsistent, "
        "-1 and -2 no usable RV.",
    ("vari_eclipsing_binary", "classification_score"): "DR4 only. Score of the classifier that chose the stars to process.",
    ("vari_eclipsing_binary", "g_num_obs"): "DR4 only. Number of G observations in the input light curve.",
    ("vari_planetary_transit", "transit_reference_time"): "Days, BJD in TCB minus 2455197.5. A mid-transit time near the middle of the "
        "Gaia data. Transit n happens at transit_reference_time + n * transit_period.",
    ("vari_planetary_transit", "transit_period"): "Days. The table has no error on the period, so predictions far from "
        "transit_reference_time cannot be given an uncertainty from this table.",
    ("vari_planetary_transit", "transit_depth"): "Milli-magnitudes.",
    ("vari_planetary_transit", "transit_duration"): "Days (not a phase fraction). Data model: a time t is in transit if "
        "abs(mod(t - T0 + P/2, P) - P/2) < w/2.",
    ("vari_planetary_transit", "num_in_transit"): "Number of Gaia observations inside transits. Integer type is narrower in DR4.",
    ("gaia_source", "teff"): "Renamed and changed in meaning. DR4 teff is the value from the module named in ap_origin "
        "(GSP-Phot, GSP-Spec and others). DR3 teff_gspphot is GSP-Phot only. Not the same quantity.",
    ("gaia_source", "ref_epoch"): "DR4 reference epoch J2017.5, DR3 J2016.0 (Gaia DR4 page). Positions and proper motions refer to it.",
    ("gaia_source", "phot_g_mean_mag"): "In DR4 the G value of an eclipsing binary can come from the eclipsing-binary model "
        "(see g_photometry_origin). Then phot_g_n_obs is 0. What the model value stands for (mean or out of eclipse) "
        "is not stated in the draft.",
    ("gaia_source", "bp_rp"): "Same definition. In DR4 BP and RP can also come from variability models (Cepheids, RR Lyrae).",
    ("gaia_source", "phot_variable_flag"): "Values VARIABLE, POSSIBLE, NON_VARIABLE or empty in the DR4 draft.",
    ("gaia_source", "g_photometry_origin"): "DR4 only. Names the table that gave the G magnitude. vari_eclipsing_binary means the "
        "EB model. Select it to know which G you have.",
    ("gaia_source", "colour_origin"): "DR4 only. Names the table that gave BP and RP.",
    ("gaia_source", "ap_origin"): "DR4 only. Which module gave teff, logg and mh.",
    ("gaia_source", "phot_bp_rp_excess_factor"): "Not in DR4 gaia_source (the draft lists no such column there).",
    ("gaia_source", "bp_g"): "Not in DR4 gaia_source. Compute phot_bp_mean_mag - phot_g_mean_mag.",
    ("gaia_source", "g_rp"): "Not in DR4 gaia_source. Compute phot_g_mean_mag - phot_rp_mean_mag.",
    ("gaia_source", "non_single_star"): "Not in DR4 gaia_source. The draft lists it in all_source_flags.",
    ("gaia_source", "duplicated_source"): "Not in DR4 gaia_source. The draft lists it in all_source_astrometry.",
    ("gaia_source", "has_epoch_photometry"): "Not in DR4 gaia_source. The draft lists has_epoch_photometry in all_source_flags.",
    ("dr3_neighbourhood", "source_id"): "DR4 ID. Stand-in column is the DR3 ID in dr2_neighbourhood.",
    ("dr3_neighbourhood", "dr3_source_id"): "The older ID. Stand-in column is the DR2 ID, which the TESS Input Catalog uses.",
    ("dr3_neighbourhood", "probable_match"): "DR4 only. True if both sources probably are the same object.",
    ("dr3_neighbourhood", "angular_distance"): "Milli-arcseconds in both.",
}

# explicit renames: (dr4 table, dr4 column) -> dr3 column
RENAMES = {
    ("gaia_source", "teff"): "teff_gspphot",
    ("dr3_neighbourhood", "source_id"): "dr3_source_id",
    ("dr3_neighbourhood", "dr3_source_id"): "dr2_source_id",
}

# units that are written differently but mean the same
UNIT_SAME = {("d**-1", "day-1"), ("d", "day"), ("mas.yr**-1", "mas yr-1"), ("um**-1", "µm-1"),
             ("'electron'.s**-1", "e- s-1"), ("km.s**-1", "km s-1"), ("yr", "Julian Years"),
             ("mas", "mas"), ("mag", "mag"), ("", "")}
ZERO_POINT_COLUMNS = {("vari_eclipsing_binary", "reference_time"), ("vari_planetary_transit", "transit_reference_time")}


def load():
    dr4 = {}
    with open(DR4_FILE, encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            dr4.setdefault(r["table"], {})[r["column"]] = r
    dr3 = {}
    with open(DR3_FILE, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            dr3.setdefault(r["table_name"].split(".")[1], {})[r["column_name"]] = r
    return dr4, dr3


def unit_check(key, u4, u3):
    if key in ZERO_POINT_COLUMNS:
        return "zero_point"
    if not u4 and not u3:
        return "n/a"
    if (u3, u4) in UNIT_SAME or u3 == u4:
        return "same"
    return "text_differs"


def main():
    dr4, dr3 = load()
    rows = []
    for t4, t3 in TABLES:
        rows.append(["table", "%s.%s" % (SCHEMA4, t4), "-", "%s.%s" % (SCHEMA3, t3), "-", "", "", "", "",
                     "same" if t4 == t3 else "renamed", "n/a", TABLE_NOTES.get(t4, "")])
        c4, c3 = dr4[t4], dr3[t3]
        renamed_dr3 = {RENAMES[(t4, c)] for c in c4 if (t4, c) in RENAMES}
        for c in c4:
            n3 = RENAMES.get((t4, c), c)
            r4 = c4[c]
            if n3 in c3:
                r3 = c3[n3]
                status = "renamed" if n3 != c else "same"
                rows.append(["column", t4, c, t3, n3, r4["unit"], r3["unit"], r4["type"], r3["datatype"], status,
                             unit_check((t4, c), r4["unit"], r3["unit"]), NOTES.get((t4, c), "")])
            else:
                rows.append(["column", t4, c, t3, "-", r4["unit"], "", r4["type"], "", "dr4_only", "n/a",
                             NOTES.get((t4, c), "")])
        for c in c3:
            if c not in c4 and c not in renamed_dr3:
                r3 = c3[c]
                rows.append(["column", t4, "-", t3, c, "", r3["unit"], "", r3["datatype"], "dr3_only", "n/a",
                             NOTES.get((t4, c), "")])
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["kind", "dr4_table", "dr4_name", "dr3_table", "dr3_name", "dr4_unit", "dr3_unit",
                    "dr4_type", "dr3_type", "status", "unit_check", "notes"])
        w.writerows(rows)
    from collections import Counter
    print("wrote %s: %d lines" % (OUT, len(rows)))
    print(Counter((r[1], r[9]) for r in rows if r[0] == "column"))


if __name__ == "__main__":
    sys.exit(main())
