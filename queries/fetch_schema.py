"""Fetch two small lists from the live Gaia archive's TAP_SCHEMA, anonymously (2 requests).

    python3 -I fetch_schema.py

Writes
  results/archive_tables.csv           every table in the archive (schema, table). Used to show that no TESS table exists.
  results/dr3_tap_schema_columns.csv   columns, types, units and descriptions of the DR3 tables used here and of the
                                       APASS and Tycho-2 tables used to check the B conversion.
build_column_map.py and check_columns.py read the second file.
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TABLES = ["gaiadr3.vari_eclipsing_binary", "gaiadr3.vari_planetary_transit", "gaiadr3.vari_planetary_transit_13june2022",
          "gaiadr3.vari_summary", "gaiadr3.gaia_source", "gaiadr3.dr2_neighbourhood", "gaiadr3.apassdr9_best_neighbour",
          "external.apassdr9", "public.tycho2", "gaiadr3.tycho2tdsc_merge_best_neighbour", "gaiadr3.tycho2tdsc_merge"]


def main():
    h, rows = common.tap_query("SELECT schema_name, table_name, description FROM TAP_SCHEMA.tables ORDER BY schema_name, table_name",
                               note="list tables")
    with open(os.path.join(HERE, "results", "archive_tables.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["schema_name", "table_name"])
        w.writerows([r[:2] for r in rows])
    print("%d tables in the archive" % len(rows))
    q = ("SELECT table_name, column_name, datatype, unit, ucd, description FROM TAP_SCHEMA.columns WHERE table_name IN (%s) "
         "ORDER BY table_name, column_index" % ",".join("'%s'" % t for t in TABLES))
    h, rows = common.tap_query(q, note="TAP_SCHEMA.columns for DR3 stand-in tables")
    with open(os.path.join(HERE, "results", "dr3_tap_schema_columns.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(h)
        w.writerows(rows)
    print("%d columns" % len(rows))


if __name__ == "__main__":
    main()
