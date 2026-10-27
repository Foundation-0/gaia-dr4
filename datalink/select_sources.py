#!/usr/bin/env python3
"""Choose the DR3 test sources for the DataLink fetcher test.

It runs four small queries on the Gaia archive's TAP service (the query
service) and writes two files into sources/:

  test_sources.csv  25 sources in four groups (see ROLE below)
  ids25.txt         the same 25 IDs with the groups mixed, in a fixed order
  ids40.txt         40 other sources with epoch photometry, for the timing runs
  pool200.txt       200 sources that have epoch photometry, for the
                    batch-size test (1, 10, 50, 200 IDs per request)

Every query answer is cached in data/tap/, so a second run sends nothing.
The queries are fixed text, and DR3 does not change, so a re-run gives the
same lists.

Usage:  python3 select_sources.py
"""
import csv
import hashlib
import io
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TAP_URL = "https://gea.esac.esa.int/tap-server/tap/sync"
USER_AGENT = "Foundation0-gaia-dr4/0.1 (+https://github.com/Foundation-0/gaia-dr4)"
CACHE = os.path.join(HERE, "data", "tap")
OUT = os.path.join(HERE, "sources")

# One query per group. ORDER BY source_id makes the answer repeatable.
QUERIES = {
    "pool": (
        "SELECT TOP 200 source_id, phot_g_mean_mag, phot_variable_flag, has_epoch_photometry "
        "FROM gaiadr3.gaia_source "
        "WHERE has_epoch_photometry = 'True' AND random_index BETWEEN 0 AND 4000000 "
        "AND phot_g_mean_mag BETWEEN 10 AND 19 ORDER BY source_id"
    ),
    "eb": (
        "SELECT TOP 8 g.source_id, g.phot_g_mean_mag, g.phot_variable_flag, g.has_epoch_photometry "
        "FROM gaiadr3.vari_eclipsing_binary AS eb JOIN gaiadr3.gaia_source AS g USING (source_id) "
        "WHERE g.has_epoch_photometry = 'True' AND g.random_index BETWEEN 0 AND 20000000 "
        "AND g.phot_g_mean_mag BETWEEN 10 AND 16 ORDER BY g.source_id"
    ),
    "no_epoch": (
        "SELECT TOP 5 source_id, phot_g_mean_mag, phot_variable_flag, has_epoch_photometry "
        "FROM gaiadr3.gaia_source "
        "WHERE has_epoch_photometry = 'False' AND random_index BETWEEN 0 AND 100000 "
        "AND phot_g_mean_mag BETWEEN 11 AND 13 ORDER BY source_id"
    ),
}

# Two IDs that are valid 64-bit numbers but are not Gaia DR3 sources.
# They test what the service says about a source that does not exist.
FAKE_IDS = ["1000000000000000", "4611686018427387904"]


def tap(query):
    """Run one query, with an on-disk cache. Returns a list of dict rows."""
    os.makedirs(CACHE, exist_ok=True)
    key = hashlib.sha256(query.encode()).hexdigest()[:16]
    path = os.path.join(CACHE, key + ".csv")
    if not os.path.exists(path):
        body = urllib.parse.urlencode({
            "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": query,
        }).encode()
        req = urllib.request.Request(TAP_URL, data=body, headers={"User-Agent": USER_AGENT})
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=90) as r:
            data = r.read()
        print("TAP %.1fs %d bytes: %s" % (time.time() - t0, len(data), query[:70]), file=sys.stderr)
        with open(path, "wb") as f:
            f.write(data)
        with open(path + ".query.txt", "w") as f:
            f.write(query + "\n")
        time.sleep(1.5)
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def main():
    os.makedirs(OUT, exist_ok=True)
    pool = tap(QUERIES["pool"])
    eb = tap(QUERIES["eb"])
    no_epoch = tap(QUERIES["no_epoch"])
    if len(pool) < 200 or len(eb) < 5 or len(no_epoch) < 5:
        sys.exit("Unexpected answer sizes: pool %d, eb %d, no_epoch %d" % (len(pool), len(eb), len(no_epoch)))

    # ROLE says what the source is for.
    #   regular   has epoch photometry, not an eclipsing binary (10, spread over the pool)
    #   eclipsing has epoch photometry, listed in gaiadr3.vari_eclipsing_binary (8)
    #   no_epoch  real DR3 source, has_epoch_photometry is false (5), failure path
    #   not_found valid number that is not a DR3 source (2), failure path
    rows = []
    for r in pool[::20][:10]:
        rows.append(("regular", r["source_id"], r["phot_g_mean_mag"], r["phot_variable_flag"], r["has_epoch_photometry"]))
    for r in eb[:8]:
        rows.append(("eclipsing", r["source_id"], r["phot_g_mean_mag"], r["phot_variable_flag"], r["has_epoch_photometry"]))
    for r in no_epoch[:5]:
        rows.append(("no_epoch", r["source_id"], r["phot_g_mean_mag"], r["phot_variable_flag"], r["has_epoch_photometry"]))
    for sid in FAKE_IDS:
        rows.append(("not_found", sid, "", "", ""))

    with open(os.path.join(OUT, "test_sources.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["role", "source_id", "phot_g_mean_mag", "phot_variable_flag", "has_epoch_photometry"])
        w.writerows(rows)
    # The same 25 IDs with the groups mixed (one of each group in turn), so that every batch
    # has sources with and without epoch photometry. This is the file the fetcher is run on.
    by_role = {r: [row[1] for row in rows if row[0] == r] for r in ("regular", "eclipsing", "no_epoch", "not_found")}
    mixed = []
    while any(by_role.values()):
        for r in by_role:
            if by_role[r]:
                mixed.append(by_role[r].pop(0))
    with open(os.path.join(OUT, "ids25.txt"), "w") as f:
        for sid in mixed:
            f.write(sid + "\n")
    # 40 more sources with epoch photometry (not used elsewhere) for the timing runs.
    with open(os.path.join(OUT, "ids40.txt"), "w") as f:
        for r in pool[150:190]:
            f.write(r["source_id"] + "\n")
    with open(os.path.join(OUT, "pool200.txt"), "w") as f:
        for r in pool:
            f.write(r["source_id"] + "\n")
    print("wrote %d test sources and %d pool sources" % (len(rows), len(pool)))


if __name__ == "__main__":
    main()
