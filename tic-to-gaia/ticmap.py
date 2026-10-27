#!/usr/bin/env python3
"""Map TESS Input Catalog (TIC) IDs to Gaia DR3 source IDs.

The route is TIC ID -> Gaia DR2 source ID (a column of the TIC) -> Gaia DR3 source ID
(the archive table gaiadr3.dr2_neighbourhood). The result is cross-checked by position.

Commands (run with `python3 -I ticmap.py <command> --help` for the options):

  targets   turn eumemic's candidates.json into a plain target file (one row per candidate)
  fetch     download what the mapping needs and save it in snapshots/ (the only step that
            uses the network; every answer is also cached under data/)
  build     make the output table from snapshots/ alone (no network)
  run       fetch, then build
  summary   print the counts of the output table

Any list of TIC IDs works: a text file with one ID per line, or a CSV with a `tic` column.

Gaia data: this work has made use of data from the European Space Agency (ESA) mission
Gaia (https://www.cosmos.esa.int/gaia), processed by the Gaia Data Processing and Analysis
Consortium (DPAC, https://www.cosmos.esa.int/web/gaia/dpac/consortium).
The TIC comes from the Mikulski Archive for Space Telescopes (MAST).
"""

import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import httpcache  # noqa: E402
import tap  # noqa: E402
from astrometry import propagate, separation_arcsec  # noqa: E402

# ---------------------------------------------------------------------------------------
# Settings. The thresholds are this project's choices. Gaia does not define them.
# ---------------------------------------------------------------------------------------

TIC_EPOCH = 2000.0   # epoch of the TIC columns `ra`, `dec` (checked in README.md)
DR2_EPOCH = 2015.5   # epoch of the TIC columns `ra_orig`, `dec_orig` (Gaia DR2 positions)
MAG_CUT = 0.1        # |G difference| below this counts as "magnitude-consistent"
                     # (the cut used in ESA's archive tutorial for dr2_neighbourhood)
DIST_FLAG_MAS = 100.0  # flag a chosen neighbour farther than this (mas)
POS_OK = 0.2         # position check: at most this many arcseconds is "ok"
POS_LARGE = 1.0      # more than this many arcseconds is "large"

TIC_COLUMNS = ["id", "version", "gaia", "ra", "dec", "pmra", "pmdec", "plx", "tmag",
               "gaiamag", "gaiaqflag", "typesrc", "objtype", "posflag", "pmflag",
               "disposition", "duplicate_id", "ra_orig", "dec_orig"]

Q_TIC = ("SELECT " + ", ".join(TIC_COLUMNS) + " FROM dbo.catalogrecord WHERE id IN ({ids})")
Q_FWD = ("SELECT dr2_source_id, dr3_source_id, angular_distance, magnitude_difference, "
         "proper_motion_propagation FROM gaiadr3.dr2_neighbourhood "
         "WHERE dr2_source_id IN ({ids}) ORDER BY dr2_source_id, angular_distance")
Q_REV = ("SELECT dr2_source_id, dr3_source_id, angular_distance, magnitude_difference, "
         "proper_motion_propagation FROM gaiadr3.dr2_neighbourhood "
         "WHERE dr3_source_id IN ({ids}) ORDER BY dr3_source_id, angular_distance")
SRC_COLUMNS = ["source_id", "ref_epoch", "ra", "dec", "pmra", "pmdec", "parallax",
               "phot_g_mean_mag", "ruwe", "astrometric_params_solved", "duplicated_source"]
Q_SRC = ("SELECT " + ", ".join(SRC_COLUMNS) + " FROM gaiadr3.gaia_source "
         "WHERE source_id IN ({ids}) ORDER BY source_id")

FWD_COLUMNS = ["dr2_source_id", "dr3_source_id", "angular_distance",
               "magnitude_difference", "proper_motion_propagation"]

OUT_COLUMNS = [
    "tic", "dr2_source_id", "dr3_source_id", "status", "n_neighbours",
    "angular_distance_mas", "magnitude_difference", "proper_motion_propagation",
    "n_mag_consistent", "runner_up_dr3_source_id", "runner_up_distance_mas",
    "runner_up_magnitude_difference", "runner_up_delta_g", "n_dr2_for_dr3",
    "pos_sep_tic_epoch_arcsec", "pos_sep_dr2_epoch_arcsec", "pos_check",
    "nearest_by_position_dr3", "flags", "needs_judgement", "judgement_reasons",
    "tic_ra", "tic_dec", "tic_pmra", "tic_pmdec", "tmag", "tic_disposition",
    "tic_gaiaqflag", "tic_pmflag",
    "dr3_pmra", "dr3_pmdec", "dr3_g", "dr3_ruwe",
]


# ---------------------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------------------

def fnum(text):
    """Float from a cell, or None if the cell is empty or not a number."""
    if text is None:
        return None
    text = str(text).strip()
    if text == "" or text.lower() in ("nan", "null", "none"):
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return None if value != value else value


def parse_bool(text):
    """True, False or None from an archive CSV cell. The Gaia archive writes 'true' and
    'false'. Some mirrors write 1 and 0, so those (and t, f) are accepted too."""
    text = (text or "").strip().lower()
    if text in ("true", "t", "1"):
        return True
    if text in ("false", "f", "0"):
        return False
    return None


def bool_cell(text, what):
    """Like parse_bool, but a cell that is neither empty nor a recognised yes/no is an error,
    so that a change of format in an archive answer cannot pass silently."""
    value = parse_bool(text)
    if value is None and (text or "").strip():
        raise ValueError("%s: expected true or false, got %r" % (what, text))
    return value


def fmt(value, digits):
    return "" if value is None else ("%.*f" % (digits, value))


def write_csv(path, names, rows):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(names)
        writer.writerows(rows)


def read_csv_dicts(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


# ---------------------------------------------------------------------------------------
# Target lists
# ---------------------------------------------------------------------------------------

def read_targets(path):
    """Return a sorted list of unique TIC IDs (ints) from a text file, CSV or eumemic JSON."""
    if path.lower().endswith(".json"):
        with open(path) as fh:
            doc = json.load(fh)
        raw = [int(t) for t in doc["tic"]]
    else:
        with open(path, newline="") as fh:
            lines = [ln for ln in fh.read().splitlines() if ln.strip() and not ln.startswith("#")]
        if not lines:
            raise ValueError("no IDs in %s" % path)
        first = next(csv.reader([lines[0]]))
        header = [c.strip().lower() for c in first]
        col = 0
        if not header[0].replace("tic", "").strip().isdigit():
            if "tic" not in header:
                raise ValueError("%s: first line is not an ID and has no 'tic' column" % path)
            col = header.index("tic")
            lines = lines[1:]
        raw = []
        for row in csv.reader(lines):
            cell = row[col].strip()
            if cell.lower().startswith("tic"):
                cell = cell[3:].strip()
            raw.append(int(cell))
    return sorted(set(raw))


def eumemic_to_csv(json_path, out_path):
    """Write one row per candidate from eumemic's candidates.json. Returns the row count."""
    with open(json_path) as fh:
        doc = json.load(fh)
    tiers, sets = doc["tiers"], ["allsky", "earlier"]
    names = ["tic", "tier", "set", "ra_deg", "dec_deg", "tmag", "period_d",
             "radius_earth", "depth_ppm"]
    rows = []
    for i, tic in enumerate(doc["tic"]):
        rows.append([tic, tiers[doc["tier"][i]], sets[doc["set"][i]], doc["ra"][i],
                     doc["dec"][i], doc["tmag"][i], doc["P"][i], doc["rp"][i],
                     doc["depth"][i]])
    write_csv(out_path, names, rows)
    return len(rows)


# ---------------------------------------------------------------------------------------
# Fetching (the only part that uses the network)
# ---------------------------------------------------------------------------------------

def _fetched_times(infos):
    times = []
    for info in infos:
        with open(os.path.join(info["folder"], "request.json")) as fh:
            times.append(json.load(fh)["fetched_utc"])
    return {"first_fetched_utc": min(times), "last_fetched_utc": max(times),
            "queries": len(times)}


def fetch_tic(ids, data_dir, offline=False):
    rows, infos = {}, []
    for batch in tap.batches(ids):
        names, got, info = tap.mast_query(data_dir, "tic", Q_TIC.format(ids=tap.id_list(batch)),
                                          offline=offline, require=TIC_COLUMNS)
        infos.append(info)
        for r in got:
            rec = dict(zip(names, r))
            tic = int(rec["id"])
            if tic in rows:
                raise ValueError("TIC %d returned twice" % tic)
            if tic not in batch:
                raise ValueError("TIC %d returned but not requested" % tic)
            rows[tic] = rec
    return rows, _fetched_times(infos)


def _fetch_neighbourhood(query, key_col, ids, kind, data_dir, offline):
    rows, infos = [], []
    for batch in tap.batches(ids):
        names, got, info = tap.gaia_query(data_dir, kind, query.format(ids=tap.id_list(batch)),
                                          offline=offline)
        if names != FWD_COLUMNS:
            raise ValueError("unexpected columns %r" % names)
        infos.append(info)
        if len(got) >= 50000:
            raise ValueError("answer reached the archive's 50,000-row limit; use smaller batches")
        wanted = set(batch)
        for r in got:
            if int(r[names.index(key_col)]) not in wanted:
                raise ValueError("row for an identifier that was not requested: %r" % r)
            rows.append(r)
    rows.sort(key=lambda r: (int(r[0]), int(r[1])))
    return rows, _fetched_times(infos)


def fetch_dr2n(dr2_ids, data_dir, offline=False):
    return _fetch_neighbourhood(Q_FWD, "dr2_source_id", dr2_ids, "dr2n", data_dir, offline)


def fetch_rev(dr3_ids, data_dir, offline=False):
    return _fetch_neighbourhood(Q_REV, "dr3_source_id", dr3_ids, "dr3rev", data_dir, offline)


def fetch_src(dr3_ids, data_dir, offline=False):
    rows, infos = [], []
    for batch in tap.batches(dr3_ids):
        names, got, info = tap.gaia_query(data_dir, "dr3src", Q_SRC.format(ids=tap.id_list(batch)),
                                          offline=offline)
        if names != SRC_COLUMNS:
            raise ValueError("unexpected columns %r" % names)
        infos.append(info)
        rows.extend(got)
    rows.sort(key=lambda r: int(r[0]))
    return rows, _fetched_times(infos)


SNAPSHOT_FILES = ["tic_records.csv", "dr2_neighbourhood.csv", "dr3_reverse_neighbourhood.csv",
                  "dr3_gaia_source.csv", "target_ids.txt"]


def file_sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def write_snapshots(snap_dir, ids, tic, fwd, rev, src, info):
    """Write the five snapshot files and run_info.json, all or nothing.

    The files are first written to a temporary folder next to snap_dir, together with a
    checksum of each in run_info.json. Only when all are written are they moved into
    snap_dir, run_info.json last. So an error in the middle leaves the old snapshots as
    they were, and load_snapshots refuses a folder whose files do not match run_info.json.
    """
    os.makedirs(snap_dir, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix=".snapshots-partial-", dir=os.path.dirname(os.path.abspath(snap_dir)))
    try:
        write_csv(os.path.join(tmp, "tic_records.csv"),
                  ["tic" if c == "id" else c for c in TIC_COLUMNS],
                  [[tic[t][c] for c in TIC_COLUMNS] for t in sorted(tic)])
        write_csv(os.path.join(tmp, "dr2_neighbourhood.csv"), FWD_COLUMNS, fwd)
        write_csv(os.path.join(tmp, "dr3_reverse_neighbourhood.csv"), FWD_COLUMNS, rev)
        write_csv(os.path.join(tmp, "dr3_gaia_source.csv"), SRC_COLUMNS, src)
        with open(os.path.join(tmp, "target_ids.txt"), "w") as fh:
            fh.write("".join("%d\n" % t for t in ids))
        info = dict(info, files={name: file_sha256(os.path.join(tmp, name))
                                 for name in SNAPSHOT_FILES})
        with open(os.path.join(tmp, "run_info.json"), "w") as fh:
            json.dump(info, fh, indent=1, sort_keys=True)
            fh.write("\n")
        for name in SNAPSHOT_FILES + ["run_info.json"]:
            os.replace(os.path.join(tmp, name), os.path.join(snap_dir, name))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return info


def fetch_all(ids, data_dir, snap_dir, offline=False):
    """Download everything for the TIC IDs `ids`, then write the snapshot files.

    Nothing is written to snap_dir until every download has worked. A download that fails
    (the network, an archive that is down) can simply be started again: answers already
    received are in data_dir and are not asked for twice.
    """
    info = {"queries": {"tic": Q_TIC, "dr2_neighbourhood": Q_FWD,
                        "dr3_reverse_neighbourhood": Q_REV, "dr3_gaia_source": Q_SRC},
            "services": {"tic": tap.MAST_TIC_TAP, "gaia": tap.GAIA_TAP},
            "batch_size": tap.BATCH}
    tic, info["tic"] = fetch_tic(ids, data_dir, offline)
    versions = sorted({r["version"] for r in tic.values()})
    info["tic"]["found"] = len(tic)
    info["tic"]["catalog_versions_seen"] = versions

    dr2_ids = sorted({int(r["gaia"]) for r in tic.values() if r["gaia"].strip()})
    fwd, info["dr2_neighbourhood"] = fetch_dr2n(dr2_ids, data_dir, offline)
    info["dr2_neighbourhood"]["dr2_ids_asked"] = len(dr2_ids)
    info["dr2_neighbourhood"]["rows"] = len(fwd)

    dr3_ids = sorted({int(r[1]) for r in fwd})
    rev, info["dr3_reverse_neighbourhood"] = fetch_rev(dr3_ids, data_dir, offline)
    info["dr3_reverse_neighbourhood"]["dr3_ids_asked"] = len(dr3_ids)
    info["dr3_reverse_neighbourhood"]["rows"] = len(rev)

    src, info["dr3_gaia_source"] = fetch_src(dr3_ids, data_dir, offline)
    info["dr3_gaia_source"]["rows"] = len(src)
    info["n_targets"] = len(ids)
    return write_snapshots(snap_dir, ids, tic, fwd, rev, src, info)


# ---------------------------------------------------------------------------------------
# Building the table (pure functions, no network)
# ---------------------------------------------------------------------------------------

def check_snapshot_files(snap_dir, info):
    """Refuse a snapshot folder whose files are not the ones run_info.json describes.

    A fetch that stopped half way, or a file edited by hand, would otherwise give a table
    that looks fine and is wrong.
    """
    sums = info.get("files")
    if not sums:
        raise ValueError("run_info.json in %s has no file checksums: it was not written by "
                         "this version of ticmap.py. Run the fetch step again." % snap_dir)
    bad = [name for name in SNAPSHOT_FILES
           if not os.path.exists(os.path.join(snap_dir, name))
           or file_sha256(os.path.join(snap_dir, name)) != sums.get(name)]
    if bad:
        raise ValueError("%s: %s do not match run_info.json. A fetch was probably stopped half "
                         "way. Run the fetch step again." % (snap_dir, ", ".join(bad)))


def load_snapshots(snap_dir):
    def path(name):
        return os.path.join(snap_dir, name)

    with open(path("run_info.json")) as fh:
        info = json.load(fh)
    check_snapshot_files(snap_dir, info)
    with open(path("target_ids.txt")) as fh:
        ids = [int(x) for x in fh.read().split()]
    tic = {int(r["tic"]): r for r in read_csv_dicts(path("tic_records.csv"))}
    fwd = {}
    for r in read_csv_dicts(path("dr2_neighbourhood.csv")):
        fwd.setdefault(int(r["dr2_source_id"]), []).append(
            {"dr3": int(r["dr3_source_id"]), "dist": fnum(r["angular_distance"]),
             "dmag": fnum(r["magnitude_difference"]),
             "pmprop": bool_cell(r["proper_motion_propagation"], "proper_motion_propagation")})
    rev = {}
    for r in read_csv_dicts(path("dr3_reverse_neighbourhood.csv")):
        rev.setdefault(int(r["dr3_source_id"]), set()).add(int(r["dr2_source_id"]))
    src = {}
    for r in read_csv_dicts(path("dr3_gaia_source.csv")):
        row = {k: fnum(r[k]) for k in SRC_COLUMNS[1:] if k != "duplicated_source"}
        row["duplicated_source"] = bool_cell(r["duplicated_source"], "duplicated_source")
        src[int(r["source_id"])] = row
    return ids, tic, fwd, rev, src, info


def position_offsets(rec, s):
    """Compare the TIC position with a DR3 source moved to the TIC epoch.

    rec is a TIC record (strings), s a DR3 source (numbers). Returns
    (separation at the TIC epoch in arcsec, separation at the DR2 epoch in arcsec,
    where the proper motion came from: 'dr3', 'tic' or 'none').
    """
    pmra, pmdec, origin = s["pmra"], s["pmdec"], "dr3"
    if pmra is None or pmdec is None:
        pmra, pmdec = fnum(rec["pmra"]), fnum(rec["pmdec"])
        origin = "tic" if pmra is not None and pmdec is not None else "none"
    epoch = s["ref_epoch"] or 2016.0
    tra, tdec = fnum(rec["ra"]), fnum(rec["dec"])
    sep = sep2 = None
    if tra is not None and tdec is not None:
        ra, dec = propagate(s["ra"], s["dec"], pmra, pmdec, TIC_EPOCH - epoch)
        sep = separation_arcsec(tra, tdec, ra, dec)
    ora, odec = fnum(rec["ra_orig"]), fnum(rec["dec_orig"])
    if ora is not None and odec is not None:
        ra, dec = propagate(s["ra"], s["dec"], pmra, pmdec, DR2_EPOCH - epoch)
        sep2 = separation_arcsec(ora, odec, ra, dec)
    return sep, sep2, origin


def pos_check_label(sep):
    if sep is None:
        return "not done"
    if sep <= POS_OK:
        return "ok"
    if sep <= POS_LARGE:
        return "check"
    return "large"


def map_one(tic_id, rec, fwd, rev, src):
    """Build one output row (a dict keyed by OUT_COLUMNS) for one TIC ID."""
    out = {c: "" for c in OUT_COLUMNS}
    out["tic"] = tic_id
    flags, reasons = [], []

    def finish(status):
        out["status"] = status
        out["flags"] = ";".join(flags)
        out["needs_judgement"] = "yes" if reasons else "no"
        out["judgement_reasons"] = ";".join(reasons)
        return out

    if rec is None:
        reasons.append("TIC ID not found in the TIC table")
        return finish("not in TIC")

    out["tic_ra"], out["tic_dec"] = rec["ra"], rec["dec"]
    out["tic_pmra"], out["tic_pmdec"], out["tmag"] = rec["pmra"], rec["pmdec"], rec["tmag"]
    out["tic_disposition"] = rec["disposition"]
    out["tic_gaiaqflag"], out["tic_pmflag"] = rec["gaiaqflag"], rec["pmflag"]
    if rec["disposition"].strip():
        flags.append("tic_disposition_" + rec["disposition"].strip().lower())
        reasons.append("TIC marks this entry as " + rec["disposition"].strip())
    if rec["duplicate_id"].strip():
        flags.append("tic_duplicate_of_" + rec["duplicate_id"].strip())
    if rec["objtype"].strip().upper() == "EXTENDED":
        flags.append("tic_extended_object")
    if rec["typesrc"].strip() and rec["typesrc"].strip() != "tmgaia2":
        flags.append("tic_typesrc_" + rec["typesrc"].strip())
    if rec["gaiaqflag"].strip() != "1":
        # The TIC's own quality flag for its Gaia information: 1 passes, 0 fails, -1 unknown.
        flags.append("tic_gaia_quality_not_passed")
        reasons.append("the TIC quality flag for its Gaia information is %s, not 1 (0 means the "
                       "check failed, -1 means not enough information)"
                       % (rec["gaiaqflag"].strip() or "empty"))
    if rec["pmflag"].strip() != "gaia2":
        flags.append("tic_proper_motion_not_from_gaia_dr2")
        reasons.append("the TIC proper motion comes from %s, not from Gaia DR2"
                       % (rec["pmflag"].strip() or "an unnamed source"))

    dr2 = rec["gaia"].strip()
    if not dr2:
        reasons.append("the TIC entry has no Gaia DR2 ID")
        return finish("no DR2 ID")
    dr2 = int(dr2)
    out["dr2_source_id"] = dr2

    nbrs = sorted(fwd.get(dr2, []), key=lambda n: (n["dist"], n["dr3"]))
    out["n_neighbours"] = len(nbrs)
    if not nbrs:
        reasons.append("no row for this DR2 ID in dr2_neighbourhood")
        return finish("no match")

    mag_ok = [n for n in nbrs if n["dmag"] is not None and abs(n["dmag"]) < MAG_CUT]
    out["n_mag_consistent"] = len(mag_ok)
    closest = nbrs[0]
    best = (mag_ok or nbrs)[0]  # the closest of the magnitude-consistent ones, else the closest
    out["dr3_source_id"] = best["dr3"]
    out["angular_distance_mas"] = fmt(best["dist"], 3)
    out["magnitude_difference"] = fmt(best["dmag"], 4)
    out["proper_motion_propagation"] = {True: "true", False: "false", None: ""}[best["pmprop"]]
    others = [n for n in nbrs if n is not best]
    if others:
        out["runner_up_dr3_source_id"] = others[0]["dr3"]
        out["runner_up_distance_mas"] = fmt(others[0]["dist"], 3)
        out["runner_up_magnitude_difference"] = fmt(others[0]["dmag"], 4)
        s2, s1 = src.get(others[0]["dr3"]), src.get(best["dr3"])
        if s2 and s1 and s2["phot_g_mean_mag"] is not None and s1["phot_g_mean_mag"] is not None:
            # G of the runner-up minus G of the chosen source, both from DR3.
            out["runner_up_delta_g"] = fmt(s2["phot_g_mean_mag"] - s1["phot_g_mean_mag"], 3)
    n_dr2 = len(rev.get(best["dr3"], set()) | {dr2})
    out["n_dr2_for_dr3"] = n_dr2

    # Position check: every candidate, then the chosen one.
    seps = {}
    for n in nbrs:
        s = src.get(n["dr3"])
        if s is not None:
            sep, sep2, origin = position_offsets(rec, s)
            seps[n["dr3"]] = (sep, sep2, origin)
    nearest = None
    if seps and all(v[0] is not None for v in seps.values()):
        nearest = min(seps, key=lambda k: (seps[k][0], k))
    chosen = seps.get(best["dr3"])
    if chosen is not None:
        out["pos_sep_tic_epoch_arcsec"] = fmt(chosen[0], 5)
        out["pos_sep_dr2_epoch_arcsec"] = fmt(chosen[1], 5)
        out["pos_check"] = pos_check_label(chosen[0])
        if chosen[2] != "dr3":
            flags.append("proper_motion_from_" + chosen[2])
    else:
        out["pos_check"] = "not done"
    s = src.get(best["dr3"])
    if s is not None:
        out["dr3_pmra"], out["dr3_pmdec"] = fmt(s["pmra"], 4), fmt(s["pmdec"], 4)
        out["dr3_g"], out["dr3_ruwe"] = fmt(s["phot_g_mean_mag"], 4), fmt(s["ruwe"], 3)
        if s["duplicated_source"] is True:
            flags.append("dr3_duplicated_source")
        if s["astrometric_params_solved"] == 3:
            flags.append("dr3_two_parameter_solution")
            reasons.append("the DR3 source has only a position (no proper motion), so a later "
                           "position match to DR4 is weak")

    # Flags and the reasons a person should look.
    if len(nbrs) > 1:
        flags.append("several_dr3_neighbours")
    if n_dr2 > 1:
        flags.append("dr3_shared_with_other_dr2")
    if best["dmag"] is None or abs(best["dmag"]) >= MAG_CUT:
        flags.append("magnitude_difference_at_least_0.1")
    if best["dist"] is not None and best["dist"] > DIST_FLAG_MAS:
        flags.append("distance_over_100_mas")
    if best["pmprop"] is not True:
        flags.append("no_proper_motion_correction_in_crossmatch")
    if out["pos_check"] == "check":
        flags.append("position_check_0.2_to_1_arcsec")
    if closest["dr3"] != best["dr3"]:
        flags.append("closest_neighbour_fails_magnitude_cut")
    if len(nbrs) > 1 and nearest is not None and nearest != best["dr3"]:
        out["nearest_by_position_dr3"] = nearest
        flags.append("position_prefers_another_neighbour")

    if len(nbrs) > 1 and (closest["dr3"] != best["dr3"] or
                          (nearest is not None and nearest != best["dr3"])):
        reasons.append("the selection rules disagree about which neighbour is the star")
    if out["pos_check"] == "large":
        reasons.append("DR3 position differs from the TIC position by more than 1 arcsec")
    if out["pos_check"] == "not done":
        reasons.append("position check could not be done")

    status = "one-to-one" if len(nbrs) == 1 and n_dr2 == 1 else "ambiguous"
    return finish(status)


def build_table(ids, tic, fwd, rev, src):
    return [map_one(t, tic.get(t), fwd, rev, src) for t in sorted(ids)]


def table_rows(rows):
    return [[r[c] for c in OUT_COLUMNS] for r in rows]


def percentile(sorted_values, q):
    if not sorted_values:
        return None
    k = (len(sorted_values) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (k - lo)


def summarize(rows):
    """Counts for the README. `rows` are output rows (dicts)."""
    out = {"targets": len(rows)}
    by_status = {}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    out["by_status"] = dict(sorted(by_status.items()))
    out["needs_judgement"] = sum(1 for r in rows if r["needs_judgement"] == "yes")
    out["by_pos_check"] = {}
    for r in rows:
        if r["status"] in ("one-to-one", "ambiguous"):
            out["by_pos_check"][r["pos_check"]] = out["by_pos_check"].get(r["pos_check"], 0) + 1
    seps = sorted(float(r["pos_sep_tic_epoch_arcsec"]) for r in rows
                  if r["pos_sep_tic_epoch_arcsec"] != "")
    out["pos_sep_tic_epoch_arcsec"] = {
        "n": len(seps), "median": percentile(seps, 0.5), "p90": percentile(seps, 0.9),
        "p99": percentile(seps, 0.99), "max": seps[-1] if seps else None}
    seps2 = sorted(float(r["pos_sep_dr2_epoch_arcsec"]) for r in rows
                   if r["pos_sep_dr2_epoch_arcsec"] != "")
    out["pos_sep_dr2_epoch_arcsec"] = {
        "n": len(seps2), "median": percentile(seps2, 0.5), "p90": percentile(seps2, 0.9),
        "p99": percentile(seps2, 0.99), "max": seps2[-1] if seps2 else None}
    flag_counts = {}
    for r in rows:
        for f in filter(None, r["flags"].split(";")):
            if f.startswith("tic_duplicate_of_"):
                f = "tic_duplicate_of_another_entry"
            flag_counts[f] = flag_counts.get(f, 0) + 1
    out["flags"] = dict(sorted(flag_counts.items()))
    return out


def build_all(snap_dir, out_path):
    ids, tic, fwd, rev, src, info = load_snapshots(snap_dir)
    rows = build_table(ids, tic, fwd, rev, src)
    write_csv(out_path, OUT_COLUMNS, table_rows(rows))
    summary = summarize(rows)
    meta = {
        "what": "One row per TIC ID: Gaia DR2 and DR3 source IDs, how the match was chosen, "
                "and a position check. Built by ticmap.py from the files in snapshots/.",
        "settings": {"magnitude_cut": MAG_CUT, "distance_flag_mas": DIST_FLAG_MAS,
                     "position_ok_arcsec": POS_OK, "position_large_arcsec": POS_LARGE,
                     "tic_epoch": TIC_EPOCH, "dr2_epoch": DR2_EPOCH},
        "download": info, "summary": summary}
    with open(os.path.splitext(out_path)[0] + ".meta.json", "w") as fh:
        json.dump(meta, fh, indent=1, sort_keys=True)
        fh.write("\n")
    return rows, summary


# ---------------------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, need_targets):
        p.add_argument("--data-dir", default=os.path.join(HERE, "data"),
                       help="where downloaded answers are saved (default: data/)")
        p.add_argument("--snap-dir", default=os.path.join(HERE, "snapshots"),
                       help="where the small CSV snapshots go. The default is the committed "
                            "snapshots/ folder, which a fetch replaces")
        p.add_argument("--out", default=os.path.join(HERE, "tic_to_gaia_dr3.csv"),
                       help="the output table. The default is the committed table, which a "
                            "build replaces")
        if need_targets:
            p.add_argument("--targets", required=True,
                           help="text file, CSV with a 'tic' column, or candidates.json")
        p.add_argument("--offline", action="store_true",
                       help="use saved answers only; fail instead of fetching")
        p.add_argument("--timeout", type=int, default=httpcache.TIMEOUT,
                       help="seconds to wait for one answer (default: %(default)s)")

    p = sub.add_parser("targets", help="eumemic candidates.json -> target CSV")
    p.add_argument("json_path")
    p.add_argument("-o", "--out", required=True)
    common(sub.add_parser("fetch", help="download and write snapshots/"), True)
    common(sub.add_parser("build", help="make the table from snapshots/"), False)
    common(sub.add_parser("run", help="fetch, then build"), True)
    common(sub.add_parser("summary", help="print counts"), False)
    args = ap.parse_args(argv)

    if args.cmd == "targets":
        n = eumemic_to_csv(args.json_path, args.out)
        print("wrote %d candidate rows to %s" % (n, args.out))
        return 0
    httpcache.TIMEOUT = args.timeout
    if args.cmd in ("fetch", "run"):
        ids = read_targets(args.targets)
        try:
            fetch_all(ids, args.data_dir, args.snap_dir, offline=args.offline)
        except httpcache.FetchError as exc:
            print("Download failed: %s\nNothing in %s was changed. Run the same command again: "
                  "answers already received are kept in %s and are not asked for twice."
                  % (exc, args.snap_dir, args.data_dir), file=sys.stderr)
            return 1
        print("fetched for %d TIC IDs; snapshots in %s" % (len(ids), args.snap_dir))
    if args.cmd in ("build", "run", "summary"):
        try:
            rows, summary = build_all(args.snap_dir, args.out)
        except (ValueError, OSError) as exc:
            print("Cannot build the table from %s: %s" % (args.snap_dir, exc), file=sys.stderr)
            return 1
        print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
