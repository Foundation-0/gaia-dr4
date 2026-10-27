#!/usr/bin/env python3
"""Check that each TIC ID in the target file is the star the target file meant.

The target file (targets_eumemic.csv) carries eumemic's own position and TESS magnitude
(Tmag) for every candidate. eumemic gives positions to 3 decimals of a degree and Tmag to
2 decimals. This script compares them with the TIC record we downloaded.

A position that differs by more than the rounding can explain, or a Tmag that differs by
more than 0.005, means the TIC ID may point at a different star. Nothing like that was
found in the committed run (see README.md).

What this does not show: eumemic took the positions from the TIC or from a catalogue built
on it, so the check cannot catch an error that is in the TIC itself.

Usage: python3 -I check_inputs.py [--targets targets_eumemic.csv] [--snap-dir snapshots]
Writes snapshots/input_check.json. No network.
"""

import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from astrometry import separation_arcsec  # noqa: E402
from ticmap import fnum, read_csv_dicts  # noqa: E402

POSITION_DECIMALS = 3   # eumemic's ra_deg, dec_deg are rounded to 0.001 degree
TMAG_DECIMALS = 2       # eumemic's tmag is rounded to 0.01 magnitude
EPSILON = 1e-6          # slack for floating-point noise


def position_limit_arcsec(dec_deg):
    """Largest separation that rounding to POSITION_DECIMALS can explain at this declination."""
    half = 0.5 * 10 ** (-POSITION_DECIMALS)               # degrees, in each coordinate
    dx = half * math.cos(math.radians(dec_deg)) * 3600.0  # arcsec on the sky, east-west
    dy = half * 3600.0                                    # arcsec, north-south
    return math.hypot(dx, dy) + EPSILON


def tmag_limit():
    return 0.5 * 10 ** (-TMAG_DECIMALS) + EPSILON


def compare_one(target, rec):
    """target: dict from the target CSV. rec: a TIC record (strings) or None.

    Returns (position difference in arcsec or None, Tmag difference or None, problems list).
    """
    if rec is None:
        return None, None, ["not in TIC"]
    problems = []
    tra, tdec = fnum(rec["ra"]), fnum(rec["dec"])
    sep = None
    if tra is None or tdec is None:
        problems.append("TIC record has no position")
    else:
        sep = separation_arcsec(float(target["ra_deg"]), float(target["dec_deg"]), tra, tdec)
        if sep > position_limit_arcsec(float(target["dec_deg"])):
            problems.append("position differs by %.2f arcsec, more than rounding explains" % sep)
    dm = None
    ttm = fnum(rec["tmag"])
    if ttm is None:
        problems.append("TIC record has no Tmag")
    else:
        dm = abs(float(target["tmag"]) - ttm)
        if dm > tmag_limit():
            problems.append("Tmag differs by %.3f" % dm)
    return sep, dm, problems


def run(targets_path, snap_dir):
    targets = read_csv_dicts(targets_path)
    tic = {int(r["tic"]): r for r in read_csv_dicts(os.path.join(snap_dir, "tic_records.csv"))}
    seps, dms, flagged = [], [], []
    for t in targets:
        sep, dm, problems = compare_one(t, tic.get(int(t["tic"])))
        if sep is not None:
            seps.append(sep)
        if dm is not None:
            dms.append(dm)
        if problems:
            flagged.append({"tic": int(t["tic"]), "problems": problems})
    seps.sort()
    dms.sort()
    return {
        "candidate_rows": len(targets),
        "distinct_tic_ids": len({int(t["tic"]) for t in targets}),
        "position_difference_arcsec": {
            "median": seps[len(seps) // 2] if seps else None, "max": seps[-1] if seps else None},
        "tmag_difference": {
            "median": dms[len(dms) // 2] if dms else None, "max": dms[-1] if dms else None},
        "rounding_limits": {"position_arcsec_at_dec_0": position_limit_arcsec(0.0),
                            "tmag": tmag_limit()},
        "flagged": flagged,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--targets", default=os.path.join(HERE, "targets_eumemic.csv"))
    ap.add_argument("--snap-dir", default=os.path.join(HERE, "snapshots"))
    ap.add_argument("--out", default=os.path.join(HERE, "snapshots", "input_check.json"))
    args = ap.parse_args(argv)
    result = run(args.targets, args.snap_dir)
    with open(args.out, "w") as fh:
        json.dump(result, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(json.dumps(result, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
