#!/usr/bin/env python3
"""Compare two fetch runs, or one run and the committed list of checksums: same files?

For each source the log (events.jsonl) of a run has a status, and for the sources with
data a SHA-256 checksum of the saved file. This script lines two such records up and
reports every difference. It reads only the logs, and the files they name.

Usage:
  python3 compare_runs.py RUN_A RUN_B
  python3 compare_runs.py RUN_A results/expected_sha256.csv      # the 25 DR3 stand-ins of 27 Oct 2026
Options: [--release "Gaia DR3"] [--structure DATAMODEL_STANDARD]

Exit status 0 if the two runs agree on every source, 1 if not.
"""
import argparse
import csv
import hashlib
import json
import os
import sys


def sha256_of(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def last_status(run, release, structure):
    out = {}
    with open(os.path.join(run, "events.jsonl")) as f:
        for line in f:
            e = json.loads(line)
            if e.get("event") == "source" and e["release"] == release and e["structure"] == structure:
                out[e["source_id"]] = e
    return out


def expected_status(path):
    """The committed checksum list, in the same shape as a run's log: {source_id: {status, sha256}}."""
    out = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            out[r["source_id"]] = {"status": r["status"], "sha256": r["sha256"]}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("run_a")
    ap.add_argument("run_b", help="a second run folder, or a CSV of expected checksums")
    ap.add_argument("--release", default="Gaia DR3")
    ap.add_argument("--structure", default="DATAMODEL_STANDARD")
    a = ap.parse_args()
    ra = last_status(a.run_a, a.release, a.structure)
    against_csv = os.path.isfile(a.run_b) and a.run_b.endswith(".csv")
    rb = expected_status(a.run_b) if against_csv else last_status(a.run_b, a.release, a.structure)
    differences = []
    same = 0
    for sid in sorted(set(ra) | set(rb)):
        ea, eb = ra.get(sid), rb.get(sid)
        if ea is None or eb is None:
            differences.append((sid, "only in one run"))
        elif ea["status"] != eb["status"]:
            differences.append((sid, "status %s vs %s" % (ea["status"], eb["status"])))
        elif ea["status"] == "ok":
            # Hash the files again rather than trusting the logged checksum.
            ha = sha256_of(os.path.join(a.run_a, ea["file"]))
            hb = eb["sha256"] if against_csv else sha256_of(os.path.join(a.run_b, eb["file"]))
            if ha != hb:
                differences.append((sid, "files differ"))
            else:
                same += 1
        else:
            same += 1
    print("%d sources in run A, %d in run B, %d identical, %d different" % (len(ra), len(rb), same, len(differences)))
    for sid, why in differences:
        print("  %s: %s" % (sid, why))
    return 1 if differences else 0


if __name__ == "__main__":
    sys.exit(main())
