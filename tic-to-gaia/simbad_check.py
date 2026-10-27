#!/usr/bin/env python3
"""Cross-check the TIC -> Gaia DR3 table against SIMBAD (anonymous, at CDS Strasbourg).

SIMBAD is an astronomical database that gives each object a number and lists every name
it is known by. For each target this script asks SIMBAD for the object that carries the
names "TIC <id>", "Gaia DR2 <id>" and "Gaia DR3 <id>" taken from our table. If SIMBAD
puts all the names it knows on one object, the mapping agrees with SIMBAD's.

It also compares SIMBAD's position with the TIC position (both are for epoch 2000).

What this does not show: SIMBAD's own TIC to Gaia link is built from the same TIC, so the
TIC -> DR2 step is not tested independently here. The DR2 -> DR3 step is: SIMBAD links
the DR3 name to the object by its own cross-match.

SIMBAD does not hold every Gaia star, so many targets are "not_in_simbad". Those are
neither confirmed nor contradicted.

The verdict says which of the three names SIMBAD knew, and whether they sit on one object:
  agree_all_three      TIC, DR2 and DR3 names all found, all on one object
  agree_tic_dr3_only   TIC and DR3 names found on one object, no DR2 name in SIMBAD
  agree_dr2_dr3_only   DR2 and DR3 names found on one object, no TIC name in SIMBAD
  agree_tic_dr2_only   TIC and DR2 names found on one object, no DR3 name in SIMBAD
  one_name_only        only one of the three names found
  not_in_simbad        none of the names found
  disagree             the names found sit on different objects

Usage: python3 -I simbad_check.py [--offline] [--timeout SECONDS]
Writes snapshots/simbad_crosscheck.csv. The 10 spot-check targets are drawn at random, with
a fixed seed, from ALL targets whatever SIMBAD answered: N_AMBIGUOUS_SPOT of them from the
ambiguous ones and the rest from the one-to-one ones. The same 10 are chosen on every run.
A person checks them by hand. SIMBAD's answer is shown next to each, but it does not decide
which are drawn.
"""

import argparse
import csv
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import httpcache  # noqa: E402
import tap  # noqa: E402
from astrometry import separation_arcsec  # noqa: E402
from ticmap import fnum, read_csv_dicts, write_csv  # noqa: E402

SEED = 20261027
N_SPOT = 10
N_AMBIGUOUS_SPOT = 4
Q = ("SELECT i.id, i.oidref, b.main_id, b.ra, b.dec FROM ident AS i "
     "JOIN basic AS b ON b.oid = i.oidref WHERE i.id IN ({names})")
COLUMNS = ["tic", "dr2_source_id", "dr3_source_id", "simbad_main_id", "simbad_oid",
           "found_tic_name", "found_dr2_name", "found_dr3_name", "verdict",
           "simbad_minus_tic_position_arcsec", "spot_check"]


def sql_name(text):
    """Quote a name for ADQL. Only names built here (digits and fixed words) reach it."""
    return "'" + text.replace("'", "''") + "'"


def check_batch(rows, data_dir, offline):
    names = []
    for r in rows:
        names += ["TIC %d" % int(r["tic"]), "Gaia DR3 %d" % int(r["dr3_source_id"]),
                  "Gaia DR2 %d" % int(r["dr2_source_id"])]
    cols, got, _ = tap.simbad_query(data_dir, "simbad", Q.format(
        names=",".join(sql_name(n) for n in names)), offline=offline)
    ix = {c: i for i, c in enumerate(cols)}
    by_name = {}
    for g in got:
        by_name[g[ix["id"]].strip()] = (g[ix["oidref"]], g[ix["main_id"]],
                                        fnum(g[ix["ra"]]), fnum(g[ix["dec"]]))
    return by_name


def verdict_for(found):
    """found: the SIMBAD object numbers returned for the names 'tic', 'dr2', 'dr3'
    (None if SIMBAD does not know that name)."""
    names = {k for k, v in found.items() if v is not None}
    if len({found[k] for k in names}) > 1:
        return "disagree"
    if names == {"tic", "dr2", "dr3"}:
        return "agree_all_three"
    if names == {"tic", "dr3"}:
        return "agree_tic_dr3_only"
    if names == {"dr2", "dr3"}:
        return "agree_dr2_dr3_only"
    if names == {"tic", "dr2"}:
        return "agree_tic_dr2_only"
    if names:
        return "one_name_only"
    return "not_in_simbad"


def choose_spot_checks(rows):
    """rows: list of dicts with tic and status. Returns a set of TIC strings.

    The draw uses every row, not only those SIMBAD confirms. A sample taken from the
    confirmed stars would be confirmed by construction and would say nothing.
    """
    rows = sorted(rows, key=lambda r: int(r["tic"]))
    ambiguous = [r["tic"] for r in rows if r["status"] == "ambiguous"]
    plain = [r["tic"] for r in rows if r["status"] == "one-to-one"]
    rng = random.Random(SEED)
    picked = rng.sample(ambiguous, min(len(ambiguous), N_AMBIGUOUS_SPOT))
    picked += rng.sample(plain, min(len(plain), N_SPOT - len(picked)))
    return set(picked)


def run(table_path, out_path, data_dir, offline, snap_dir=None):
    snap_dir = snap_dir or os.path.dirname(out_path)
    table = [r for r in read_csv_dicts(table_path) if r["status"] in ("one-to-one", "ambiguous")]
    tic_rec = {int(r["tic"]): r for r in read_csv_dicts(os.path.join(snap_dir, "tic_records.csv"))}
    results = []
    for batch in tap.batches(table, 100):
        by_name = check_batch(batch, data_dir, offline)
        for r in batch:
            keys = {"tic": "TIC %d" % int(r["tic"]), "dr2": "Gaia DR2 %d" % int(r["dr2_source_id"]),
                    "dr3": "Gaia DR3 %d" % int(r["dr3_source_id"])}
            hit = {k: by_name.get(v) for k, v in keys.items()}
            found = {k: (h[0] if h else None) for k, h in hit.items()}
            first = next((h for h in (hit["tic"], hit["dr3"], hit["dr2"]) if h), None)
            sep = None
            rec = tic_rec[int(r["tic"])]
            if first and first[2] is not None and fnum(rec["ra"]) is not None:
                sep = separation_arcsec(first[2], first[3], fnum(rec["ra"]), fnum(rec["dec"]))
            results.append({
                "tic": r["tic"], "status": r["status"], "dr2": r["dr2_source_id"],
                "dr3": r["dr3_source_id"], "main_id": first[1] if first else "",
                "oid": first[0] if first else "", "hit": hit, "sep": sep,
                "verdict": verdict_for(found)})
    results.sort(key=lambda r: int(r["tic"]))
    spot = choose_spot_checks(results)
    out = [[r["tic"], r["dr2"], r["dr3"], r["main_id"], r["oid"],
            "yes" if r["hit"]["tic"] else "no", "yes" if r["hit"]["dr2"] else "no",
            "yes" if r["hit"]["dr3"] else "no", r["verdict"],
            "" if r["sep"] is None else "%.4f" % r["sep"],
            "yes" if r["tic"] in spot else ""] for r in results]
    write_csv(out_path, COLUMNS, out)
    counts = {}
    for r in out:
        counts[r[8]] = counts.get(r[8], 0) + 1
    return out, dict(sorted(counts.items()))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--table", default=os.path.join(HERE, "tic_to_gaia_dr3.csv"))
    ap.add_argument("--out", default=os.path.join(HERE, "snapshots", "simbad_crosscheck.csv"))
    ap.add_argument("--data-dir", default=os.path.join(HERE, "data"))
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--timeout", type=int, default=httpcache.TIMEOUT,
                    help="seconds to wait for one answer (default: %(default)s)")
    args = ap.parse_args(argv)
    httpcache.TIMEOUT = args.timeout
    out, counts = run(args.table, args.out, args.data_dir, args.offline)
    print("checked %d targets: %s" % (len(out), counts))
    print("spot-check targets:")
    for r in out:
        if r[10]:
            print("  TIC %s  Gaia DR3 %s  SIMBAD: %s  verdict: %s  position difference: %s arcsec"
                  % (r[0], r[2], r[3], r[8], r[9]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
