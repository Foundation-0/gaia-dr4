#!/usr/bin/env python3
"""Do DATAMODEL_STANDARD and DATAMODEL_GAIA hold the same numbers for the same stars?

Reads two finished fetch runs (one per structure) and, for every source that has data
in both, compares the epochs: the same number of rows, and the same transit_id, G time,
G flux, G magnitude, BP time and RP time at every epoch (to 1e-9 relative). It reads
only the files the two runs saved.

Usage:  python3 cross_check_structures.py RUN_STANDARD RUN_GAIA [--release "Gaia DR3"]
"""
import argparse
import csv
import io
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python3 -I does not add it
import gaia_datalink as g  # noqa: E402

COLUMNS = ["transit_id", "g_transit_time", "g_transit_flux", "g_transit_mag", "bp_obs_time", "rp_obs_time"]


def ok_files(run, release, structure):
    state = g.Store(run).state(release, structure)
    return {sid: os.path.join(run, e["file"]) for sid, e in state.items() if e["status"] == "ok"}


def same(a, b):
    if a in ("", "NaN", "nan", "null") or b in ("", "NaN", "nan", "null"):
        return (a in ("", "NaN", "nan", "null")) and (b in ("", "NaN", "nan", "null"))
    return math.isclose(float(a), float(b), rel_tol=1e-9)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("run_standard")
    ap.add_argument("run_gaia")
    ap.add_argument("--release", default="Gaia DR3")
    a = ap.parse_args()
    std = ok_files(a.run_standard, a.release, "DATAMODEL_STANDARD")
    gaia = ok_files(a.run_gaia, a.release, "DATAMODEL_GAIA")
    problems = []
    for sid in sorted(set(std) | set(gaia)):
        if sid not in std or sid not in gaia:
            problems.append("%s: data in only one structure" % sid)
            continue
        with open(std[sid], newline="") as f:
            srows = list(csv.DictReader(f))
        with open(gaia[sid], newline="") as f:
            grow = next(csv.DictReader(f))
        n = int(grow["n_transits"])
        if n != len(srows):
            problems.append("%s: %d rows in STANDARD, n_transits %d in GAIA" % (sid, len(srows), n))
            continue
        for col in COLUMNS:
            arr = g.parse_array(grow[col])
            for i, (x, y) in enumerate(zip((r[col] for r in srows), arr)):
                if not same(x, y):
                    problems.append("%s: %s differs at epoch %d (%s vs %s)" % (sid, col, i, x, y))
                    break
    both = len(set(std) & set(gaia))
    print("%d sources with data in both structures, %d problems" % (both, len(problems)))
    for p in problems:
        print("  " + p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
