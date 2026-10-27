#!/usr/bin/env python3
"""Link Gaia DR3 source IDs to the next release (DR4), two ways.

  Route 1 (UNTESTED against the real table): through gaiadr4.dr3_neighbourhood.
          The table does not exist before 2 December 2026. The functions here are tested
          only on made-up rows. Check the names against the published data model first.

  Route 2 (fallback, tested with DR3 as a stand-in): by position. Move each DR3 position
          to the DR4 reference epoch (J2017.5) with the DR3 proper motion, search the
          DR4 `gaia_source` table within a radius, and pick the closest source whose
          brightness is consistent. The same code, with other epochs, was tested today
          by predicting DR3 positions from the TIC's Gaia DR2 positions (see README.md).
          DR4's `gaia_source` holds only sources with good astrometry and photometry. For a
          target it does not find, `position-queries --all-sources` searches the complete
          tables `all_source_astrometry` and `all_source_photometry` instead (UNTESTED).

Commands:
  neighbourhood-queries  write ADQL batches for route 1
  match-neighbourhood    choose a DR4 source for each target from downloaded route 1 answers
  position-queries       write ADQL batches for route 2 (all targets, or only those in --tic-list)
  match-positions        choose a DR4 source for each target from downloaded cone-search answers
  compare-routes         put the two routes side by side and mark agreement
  standin-test           the DR3 stand-in test of route 2 (needs the archive; about 4 queries)

Run with `python3 -I release_day/dr4_link.py <command> --help`.

Gaia data: this work has made use of data from the European Space Agency (ESA) mission
Gaia (https://www.cosmos.esa.int/gaia), processed by the Gaia Data Processing and Analysis
Consortium (DPAC, https://www.cosmos.esa.int/web/gaia/dpac/consortium).
"""

import argparse
import csv
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import tap  # noqa: E402
from astrometry import propagate, separation_arcsec  # noqa: E402
from ticmap import fnum, parse_bool, read_csv_dicts, read_targets, write_csv  # noqa: E402

EPOCH_DR3 = 2016.0
EPOCH_DR4 = 2017.5  # Gaia DR4 reference epoch (ESA DR4 page, last updated 14 Sep 2026)
RADIUS_ARCSEC = 2.0  # the radius Gaia used to build dr2_neighbourhood
# Gaia's own "probable match" window for DR4 minus DR3 (draft data model, section 7.3).
WINDOW = (-0.25, 0.35)
PROBABLE_MAX_MAS = 60.0  # the draft's astrometric limit for probable_match
NEIGHBOURHOOD_PREFIX = "dr3_to_dr4_batch_"  # names of the query files that are written
POSITION_PREFIX = "position_batch_"


# ---------------------------------------------------------------------------------------
# Route 1: through gaiadr4.dr3_neighbourhood (UNTESTED against the real table)
# ---------------------------------------------------------------------------------------

NEIGHBOURHOOD_QUERY = (
    "SELECT n.dr3_source_id, n.source_id AS dr4_source_id, n.angular_distance, "
    "n.magnitude_difference, n.proper_motion_propagation, n.probable_match "
    "FROM gaiadr4.dr3_neighbourhood AS n WHERE n.dr3_source_id IN ({ids}) "
    "ORDER BY n.dr3_source_id, n.angular_distance")


def neighbourhood_query(dr3_ids):
    return NEIGHBOURHOOD_QUERY.format(ids=tap.id_list(dr3_ids))


def is_probable(dist_mas, dmag):
    """Gaia's probable_match rule from the draft data model, for a row without the column."""
    return (dist_mas is not None and dmag is not None and dist_mas < PROBABLE_MAX_MAS
            and WINDOW[0] <= dmag <= WINDOW[1])


def choose_from_neighbourhood(candidates):
    """candidates: list of dicts with dr4, dist (mas), dmag, probable (bool or None).

    Returns (chosen dict or None, status). Rule: among the probable matches take the
    closest; if there are none, there is no match. The status is 'one-to-one' only when
    exactly one DR4 source is listed; otherwise 'ambiguous'. The reverse check (does the
    DR4 source belong to other DR3 sources too?) is made by the caller.
    """
    if not candidates:
        return None, "no match"
    cands = sorted(candidates, key=lambda c: (c["dist"], c["dr4"]))
    probable = [c for c in cands if (c["probable"] if c["probable"] is not None
                                     else is_probable(c["dist"], c["dmag"]))]
    if not probable:
        return None, "no match"
    status = "one-to-one" if len(cands) == 1 else "ambiguous"
    return probable[0], status


# ---------------------------------------------------------------------------------------
# Route 2: by position
# ---------------------------------------------------------------------------------------

def expected_position(row, from_epoch, to_epoch):
    """Where the star should be at to_epoch. row has ra, dec, pmra, pmdec (numbers or None)."""
    return propagate(row["ra"], row["dec"], row["pmra"], row["pmdec"], to_epoch - from_epoch)


def _cone_terms(targets, radius_arcsec, ra_col="ra", dec_col="dec"):
    if not targets:
        raise ValueError("no targets")
    return " OR ".join(
        "1=CONTAINS(POINT('ICRS', %s, %s), CIRCLE('ICRS', %.9f, %.9f, %.9f))"
        % (ra_col, dec_col, float(ra), float(dec), radius_arcsec / 3600.0) for ra, dec in targets)


def cone_query(targets, table, radius_arcsec=RADIUS_ARCSEC):
    """ADQL that returns every source of `table` within the radius of any target position.

    A cone query asks for every source inside a circle on the sky. Here there is one circle
    around each target.
    targets: list of (ra, dec) in degrees at the epoch of `table`.
    """
    return ("SELECT source_id, ra, dec, pmra, pmdec, phot_g_mean_mag, ruwe, ref_epoch "
            "FROM %s WHERE %s" % (table, _cone_terms(targets, radius_arcsec)))


# DR4's gaia_source holds only the sources that pass Gaia's quality criteria. The complete
# list is in these two tables (draft data model, sections 1.1, 2.1 and 2.4). Untested.
ALL_SOURCE_ASTROMETRY = "gaiadr4.all_source_astrometry"
ALL_SOURCE_PHOTOMETRY = "gaiadr4.all_source_photometry"


def cone_query_all_sources(targets, radius_arcsec=RADIUS_ARCSEC,
                           astrometry=ALL_SOURCE_ASTROMETRY, photometry=ALL_SOURCE_PHOTOMETRY):
    """Like cone_query, on the complete DR4 tables. Returns the same columns, so that
    match-positions can read the answer. UNTESTED against the real tables.

    The G magnitude lives in the photometry table, so the two are joined. A source with no
    photometry row is kept (LEFT JOIN) and has an empty G.
    """
    return ("SELECT a.source_id AS source_id, a.ra AS ra, a.dec AS dec, a.pmra AS pmra, "
            "a.pmdec AS pmdec, p.phot_g_mean_mag AS phot_g_mean_mag, a.ruwe AS ruwe, "
            "a.ref_epoch AS ref_epoch FROM %s AS a LEFT JOIN %s AS p ON p.source_id = a.source_id "
            "WHERE %s" % (astrometry, photometry, _cone_terms(targets, radius_arcsec, "a.ra", "a.dec")))


def match_by_position(expected, candidates, radius_arcsec=RADIUS_ARCSEC, window=WINDOW):
    """Pick the source that matches one expected position.

    expected: dict with ra, dec (at the epoch of the candidates) and g (the star's G in the
              older release, or None).
    candidates: list of dicts with source_id, ra, dec, g.
    Returns (chosen candidate dict with 'sep_arcsec', status, n_in_radius).
    Rule: keep sources within the radius; if G is known, keep those whose G minus the
    old G lies in `window`; take the closest. 'one-to-one' if exactly one source lies in
    the radius, else 'ambiguous'; 'no match' if none is left.
    """
    near = []
    for c in candidates:
        sep = separation_arcsec(expected["ra"], expected["dec"], c["ra"], c["dec"])
        if sep <= radius_arcsec:
            near.append(dict(c, sep_arcsec=sep))
    if not near:
        return None, "no match", 0
    ok = near
    if expected.get("g") is not None:
        ok = [c for c in near if c["g"] is not None
              and window[0] <= c["g"] - expected["g"] <= window[1]]
    if not ok:
        return None, "no match", len(near)
    ok.sort(key=lambda c: (c["sep_arcsec"], c["source_id"]))
    return ok[0], ("one-to-one" if len(near) == 1 else "ambiguous"), len(near)


def parse_cone_answer(names, rows):
    """Read a cone-search answer. `ref_epoch` is the date the source's position is for. It is
    None if the answer has no such column."""
    ix = {n: i for i, n in enumerate(names)}
    return [{"source_id": int(r[ix["source_id"]]), "ra": float(r[ix["ra"]]),
             "dec": float(r[ix["dec"]]), "g": fnum(r[ix["phot_g_mean_mag"]]),
             "ref_epoch": fnum(r[ix["ref_epoch"]]) if "ref_epoch" in ix else None}
            for r in rows]


# ---------------------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------------------

def read_table(path):
    return [r for r in read_csv_dicts(path) if r["status"] in ("one-to-one", "ambiguous")]


def check_every_query_has_an_answer(directory, prefix):
    """Stop if a query file in `directory` has no answer file with the same number.

    Query files are named <prefix>NNN.adql and answers answer_NNN.csv. A batch whose answer
    was forgotten (or saved under another name) would otherwise show up as targets with no
    match, which looks like a real finding. Returns the number of query files found.
    """
    queries = sorted(n for n in os.listdir(directory)
                     if n.startswith(prefix) and n.endswith(".adql"))
    missing = []
    for q in queries:
        answer = "answer_%s.csv" % q[len(prefix):-len(".adql")]
        if not os.path.exists(os.path.join(directory, answer)):
            missing.append(answer)
    if missing:
        raise ValueError("%d of %d query files in %s have no answer. Missing: %s"
                         % (len(missing), len(queries), directory, ", ".join(missing)))
    if not queries:
        print("note: no %s*.adql files in %s, so it cannot be checked that every batch has an "
              "answer" % (prefix, directory), file=sys.stderr)
    return len(queries)


def cmd_neighbourhood_queries(args):
    rows = read_table(args.table)
    ids = sorted({int(r["dr3_source_id"]) for r in rows})
    os.makedirs(args.out_dir, exist_ok=True)
    n = 0
    for i, batch in enumerate(tap.batches(ids, args.batch)):
        with open(os.path.join(args.out_dir, NEIGHBOURHOOD_PREFIX + "%03d.adql" % i), "w") as fh:
            fh.write("-- UNTESTED: gaiadr4.dr3_neighbourhood does not exist before release.\n")
            fh.write(neighbourhood_query(batch) + "\n")
        n += 1
    print("wrote %d query files for %d DR3 IDs to %s" % (n, len(ids), args.out_dir))


def target_positions(table_path, snap_dir, to_epoch):
    """Expected DR4-epoch positions of the chosen DR3 sources, from the DR3 snapshot.

    The proper motion is the DR3 one. A DR3 source with only a position has none, so the
    TIC's proper motion is used instead, and the row says so in 'pm_from' ('dr3', 'tic' or
    'none'). The TIC takes its proper motion from Gaia DR2 for nearly all stars, but not for
    all: for TIC 370244729, the one star that needs this fallback, the TIC's own flag
    `pmflag` says 'tgas' (the Tycho-Gaia solution).
    """
    src = {int(r["source_id"]): r for r in read_csv_dicts(os.path.join(snap_dir, "dr3_gaia_source.csv"))}
    tic_path = os.path.join(snap_dir, "tic_records.csv")
    tic = ({int(r["tic"]): r for r in read_csv_dicts(tic_path)} if os.path.exists(tic_path) else {})
    out = []
    for r in read_table(table_path):
        s = src[int(r["dr3_source_id"])]
        pmra, pmdec, pm_from = fnum(s["pmra"]), fnum(s["pmdec"]), "dr3"
        if pmra is None or pmdec is None:
            t = tic.get(int(r["tic"]))
            pmra, pmdec = (fnum(t["pmra"]), fnum(t["pmdec"])) if t else (None, None)
            pm_from = "tic" if pmra is not None and pmdec is not None else "none"
        row = {"ra": float(s["ra"]), "dec": float(s["dec"]), "pmra": pmra, "pmdec": pmdec}
        ra, dec = expected_position(row, float(s["ref_epoch"]), to_epoch)
        out.append({"tic": r["tic"], "dr3": int(r["dr3_source_id"]), "ra": ra, "dec": dec,
                    "g": fnum(s["phot_g_mean_mag"]), "pm_from": pm_from})
    return out


def cmd_position_queries(args):
    targets = target_positions(args.table, args.snap_dir, EPOCH_DR4)
    if args.tic_list:
        wanted = set(read_targets(args.tic_list))
        targets = [t for t in targets if int(t["tic"]) in wanted]
        unknown = wanted - {int(t["tic"]) for t in targets}
        if unknown:
            raise ValueError("not in the table: TIC %s" % ", ".join(str(t) for t in sorted(unknown)))
    os.makedirs(args.out_dir, exist_ok=True)
    n = 0
    for i, batch in enumerate(tap.batches(targets, args.batch)):
        positions = [(t["ra"], t["dec"]) for t in batch]
        with open(os.path.join(args.out_dir, POSITION_PREFIX + "%03d.adql" % i), "w") as fh:
            if args.all_sources:
                fh.write("-- UNTESTED. Fallback by position at J2017.5, on the complete tables\n")
                fh.write("-- %s joined to %s.\n" % (ALL_SOURCE_ASTROMETRY, ALL_SOURCE_PHOTOMETRY))
                query = cone_query_all_sources(positions)
            else:
                fh.write("-- Fallback by position at J2017.5. Run on %s.\n" % args.dr4_table)
                query = cone_query(positions, args.dr4_table)
            fh.write("-- Save the answer as CSV next to this file, then run match-positions.\n")
            fh.write(query + "\n")
        n += 1
    with open(os.path.join(args.out_dir, "expected_positions.csv"), "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["tic", "dr3_source_id", "ra_j2017_5", "dec_j2017_5", "dr3_g", "pm_from"])
        for t in targets:
            w.writerow([t["tic"], t["dr3"], "%.9f" % t["ra"], "%.9f" % t["dec"],
                        "" if t["g"] is None else "%.4f" % t["g"], t["pm_from"]])
    print("wrote %d query files and expected_positions.csv to %s" % (n, args.out_dir))


NEIGHBOURHOOD_COLUMNS = ["dr3_source_id", "dr4_source_id", "angular_distance",
                         "magnitude_difference", "proper_motion_propagation"]  # probable_match is optional
MATCH_NEIGHBOURHOOD_COLUMNS = [
    "tic", "dr3_source_id", "dr4_source_id", "status", "n_neighbours", "n_probable",
    "angular_distance_mas", "magnitude_difference", "probable_match", "same_id_as_dr3",
    "n_targets_sharing_dr4", "needs_judgement", "judgement_reasons"]


def read_neighbourhood_answers(directory):
    """Read every answer_*.csv in `directory`. Returns {dr3_source_id: [candidate dicts]}.

    Refuses to go on if a file lacks one of the columns in NEIGHBOURHOOD_COLUMNS: on release
    day that means the published data model differs from the draft, and a person should
    look before anything is chosen.
    """
    by_dr3, n_files = {}, 0
    for name in sorted(os.listdir(directory)):
        if not (name.startswith("answer_") and name.endswith(".csv")):
            continue
        n_files += 1
        with open(os.path.join(directory, name), newline="") as fh:
            rows = list(csv.reader(fh))
        if not rows:
            raise ValueError("%s is empty" % name)
        names = rows[0]
        missing = [c for c in NEIGHBOURHOOD_COLUMNS if c not in names]
        if missing:
            raise ValueError("%s lacks column(s) %s: compare with the published data model"
                             % (name, ", ".join(missing)))
        ix = {c: names.index(c) for c in names}
        for r in rows[1:]:
            cand = {"dr4": int(r[ix["dr4_source_id"]]), "dist": fnum(r[ix["angular_distance"]]),
                    "dmag": fnum(r[ix["magnitude_difference"]]),
                    "pmprop": parse_bool(r[ix["proper_motion_propagation"]]),
                    "probable": parse_bool(r[ix["probable_match"]]) if "probable_match" in ix else None}
            if cand["dist"] is None:
                raise ValueError("%s: a row has no angular_distance" % name)
            by_dr3.setdefault(int(r[ix["dr3_source_id"]]), []).append(cand)
    if not n_files:
        raise ValueError("no answer_*.csv files in %s" % directory)
    return by_dr3


def match_neighbourhood(targets, by_dr3):
    """targets: list of (tic, dr3 id) pairs. Returns output rows (lists), one per target.

    Rule (choose_from_neighbourhood): the closest probable match. 'one-to-one' only if the
    table lists exactly one DR4 source for the DR3 source and no other target in this list
    chose the same DR4 source. Anything else is 'ambiguous', and 'no match' if no probable
    match exists. A person looks at every row that is not one-to-one with a single
    probable match.
    """
    chosen = {}
    for tic, dr3 in targets:
        chosen[(tic, dr3)] = choose_from_neighbourhood(by_dr3.get(dr3, []))
    taken = {}
    for (tic, dr3), (best, _) in chosen.items():
        if best is not None:
            taken[best["dr4"]] = taken.get(best["dr4"], 0) + 1
    out = []
    for tic, dr3 in targets:
        cands = by_dr3.get(dr3, [])
        best, status = chosen[(tic, dr3)]
        n_prob = sum(1 for c in cands if (c["probable"] if c["probable"] is not None
                                          else is_probable(c["dist"], c["dmag"])))
        reasons = []
        if best is None:
            reasons.append("no probable DR4 counterpart" if cands else "DR3 ID absent from the table")
            out.append([tic, dr3, "", status if cands else "no match", len(cands), n_prob, "", "",
                        "", "", "", "yes", ";".join(reasons)])
            continue
        shared = taken[best["dr4"]]
        if shared > 1:
            status = "ambiguous"
            reasons.append("another target in the list chose the same DR4 source")
        if n_prob > 1:
            reasons.append("several probable matches")
        if best["pmprop"] is False:
            reasons.append("DR4 source has no proper motion, so its distance is less reliable")
        out.append([tic, dr3, best["dr4"], status, len(cands), n_prob, "%.3f" % best["dist"],
                    "" if best["dmag"] is None else "%.4f" % best["dmag"],
                    {True: "true", False: "false", None: "computed"}[best["probable"]],
                    "yes" if best["dr4"] == dr3 else "no", shared,
                    "yes" if reasons else "no", ";".join(reasons)])
    return out


def cmd_match_neighbourhood(args):
    check_every_query_has_an_answer(args.dir, NEIGHBOURHOOD_PREFIX)
    targets = [(r["tic"], int(r["dr3_source_id"])) for r in read_table(args.table)]
    rows = match_neighbourhood(targets, read_neighbourhood_answers(args.dir))
    write_csv(args.out, MATCH_NEIGHBOURHOOD_COLUMNS, rows)
    by_status = {}
    for r in rows:
        by_status[r[3]] = by_status.get(r[3], 0) + 1
    print("wrote %s: %s" % (args.out, dict(sorted(by_status.items()))))


def compare_routes(by_neighbourhood, by_position):
    """Join the two routes by TIC. Both arguments are lists of dicts read from their CSV files.

    Returns rows [tic, dr3, dr4 by neighbourhood, dr4 by position, agreement]. The
    agreement is 'agree', 'disagree', 'only neighbourhood', 'only position' or 'neither'.
    """
    n = {r["tic"]: r for r in by_neighbourhood}
    p = {r["tic"]: r for r in by_position}
    out = []
    for tic in sorted(set(n) | set(p), key=int):
        a = (n.get(tic) or {}).get("dr4_source_id", "")
        b = (p.get(tic) or {}).get("dr4_source_id_by_position", "")
        dr3 = (n.get(tic) or p.get(tic) or {}).get("dr3_source_id", "")
        if a and b:
            verdict = "agree" if a == b else "disagree"
        elif a:
            verdict = "only neighbourhood"
        elif b:
            verdict = "only position"
        else:
            verdict = "neither"
        out.append([tic, dr3, a, b, verdict])
    return out


def cmd_compare_routes(args):
    rows = compare_routes(read_csv_dicts(args.neighbourhood), read_csv_dicts(args.positions))
    write_csv(args.out, ["tic", "dr3_source_id", "dr4_by_neighbourhood", "dr4_by_position",
                         "agreement"], rows)
    counts = {}
    for r in rows:
        counts[r[4]] = counts.get(r[4], 0) + 1
    print("wrote %s: %s" % (args.out, dict(sorted(counts.items()))))


def cmd_match_positions(args):
    check_every_query_has_an_answer(args.dir, POSITION_PREFIX)
    expected = read_csv_dicts(os.path.join(args.dir, "expected_positions.csv"))
    cands = []
    for name in sorted(os.listdir(args.dir)):
        if name.startswith("answer_") and name.endswith(".csv"):
            with open(os.path.join(args.dir, name), newline="") as fh:
                rows = list(csv.reader(fh))
            if not rows:
                raise ValueError("%s is empty" % name)
            cands += parse_cone_answer(rows[0], rows[1:])
    seen, uniq = set(), []
    for c in cands:  # one cone answer can repeat a source that lies in two cones
        if c["source_id"] not in seen:
            seen.add(c["source_id"])
            uniq.append(c)
    out = []
    for e in expected:
        exp = {"ra": float(e["ra_j2017_5"]), "dec": float(e["dec_j2017_5"]),
               "g": fnum(e["dr3_g"])}
        best, status, n = match_by_position(exp, uniq, args.radius)
        out.append([e["tic"], e["dr3_source_id"], best["source_id"] if best else "", status, n,
                    "" if not best else "%.4f" % best["sep_arcsec"],
                    "" if not best or best.get("ref_epoch") is None else "%g" % best["ref_epoch"]])
    write_csv(args.out, ["tic", "dr3_source_id", "dr4_source_id_by_position", "status",
                         "n_in_radius", "separation_arcsec", "ref_epoch"], out)
    odd = [r for r in out if r[6] not in ("", "2017.5")]
    print("wrote %s" % args.out)
    if odd:
        shown = ", ".join(r[0] for r in odd[:10]) + (", ..." if len(odd) > 10 else "")
        print("note: %d chosen source(s) have a ref_epoch other than 2017.5 (TIC %s). Their "
              "position is for another date, so a person looks. The column ref_epoch in %s "
              "has all of them." % (len(odd), shown, args.out))


def cmd_standin_test(args):
    """Test route 2 on DR3 as a stand-in for DR4.

    The 'older release' is the TIC, whose ra_orig, dec_orig are Gaia DR2 positions at
    J2015.5 and whose proper motions are Gaia DR2's (for all but one star: the TIC's
    `pmflag` for TIC 370244729 is 'tgas'). Each is moved to J2016.0 and searched in
    gaiadr3.gaia_source. The answer should be the DR3 source in tic_to_gaia_dr3.csv.
    """
    table = read_table(args.table)
    tic = {int(r["tic"]): r for r in read_csv_dicts(os.path.join(args.snap_dir, "tic_records.csv"))}
    ambiguous = [r for r in table if r["status"] == "ambiguous"]
    rest = [r for r in table if r["status"] != "ambiguous"]
    sample = ambiguous + random.Random(args.seed).sample(rest, args.n - len(ambiguous))
    sample.sort(key=lambda r: int(r["tic"]))
    targets = []
    for r in sample:
        t = tic[int(r["tic"])]
        row = {"ra": float(t["ra_orig"]), "dec": float(t["dec_orig"]),
               "pmra": fnum(t["pmra"]), "pmdec": fnum(t["pmdec"])}
        ra, dec = expected_position(row, 2015.5, EPOCH_DR3)
        targets.append({"tic": r["tic"], "expect": r["dr3_source_id"], "ra": ra, "dec": dec,
                        "g": fnum(t["gaiamag"])})
    cands = {}
    for k, batch in enumerate(tap.batches(targets, 25)):
        names, rows, _ = tap.gaia_query(
            args.data_dir, "standin",
            cone_query([(t["ra"], t["dec"]) for t in batch], "gaiadr3.gaia_source"))
        for c in parse_cone_answer(names, rows):
            cands[c["source_id"]] = c
    out, agree = [], 0
    for t in targets:
        best, status, n = match_by_position(t, list(cands.values()))
        same = best is not None and str(best["source_id"]) == t["expect"]
        agree += same
        out.append([t["tic"], t["expect"], best["source_id"] if best else "", status, n,
                    "" if not best else "%.4f" % best["sep_arcsec"], "yes" if same else "no"])
    write_csv(args.out, ["tic", "dr3_in_table", "dr3_by_position", "status", "n_in_radius",
                         "separation_arcsec", "same"], out)
    print("stand-in test: %d of %d targets give the same DR3 source as the table" % (agree, len(out)))
    by_status = {}
    for r in out:
        by_status[r[3]] = by_status.get(r[3], 0) + 1
    print("status by position:", dict(sorted(by_status.items())))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    table_default = os.path.join(ROOT, "tic_to_gaia_dr3.csv")
    snap_default = os.path.join(ROOT, "snapshots")

    p = sub.add_parser("neighbourhood-queries")
    p.add_argument("--table", default=table_default)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--batch", type=int, default=tap.BATCH)

    p = sub.add_parser("match-neighbourhood")
    p.add_argument("--table", default=table_default)
    p.add_argument("--dir", required=True, help="folder with the answer_*.csv files of route 1")
    p.add_argument("--out", required=True)

    p = sub.add_parser("compare-routes")
    p.add_argument("--neighbourhood", required=True, help="output of match-neighbourhood")
    p.add_argument("--positions", required=True, help="output of match-positions")
    p.add_argument("--out", required=True)

    p = sub.add_parser("position-queries")
    p.add_argument("--table", default=table_default)
    p.add_argument("--snap-dir", default=snap_default)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--batch", type=int, default=25)
    p.add_argument("--dr4-table", default="gaiadr4.gaia_source")
    p.add_argument("--all-sources", action="store_true",
                   help="search the complete tables all_source_astrometry and "
                        "all_source_photometry instead of gaia_source (UNTESTED)")
    p.add_argument("--tic-list", help="text file with one TIC ID per line: write queries for "
                                      "these targets only (for example the ones with no match)")

    p = sub.add_parser("match-positions")
    p.add_argument("--dir", required=True, help="folder with expected_positions.csv and answer_*.csv")
    p.add_argument("--out", required=True)
    p.add_argument("--radius", type=float, default=RADIUS_ARCSEC)

    p = sub.add_parser("standin-test")
    p.add_argument("--table", default=table_default)
    p.add_argument("--snap-dir", default=snap_default)
    p.add_argument("--data-dir", default=os.path.join(ROOT, "data"))
    p.add_argument("--out", default=os.path.join(ROOT, "snapshots", "standin_position_test.csv"))
    p.add_argument("--n", type=int, default=100)
    p.add_argument("--seed", type=int, default=20261027)

    args = ap.parse_args(argv)
    {"neighbourhood-queries": cmd_neighbourhood_queries,
     "match-neighbourhood": cmd_match_neighbourhood, "compare-routes": cmd_compare_routes,
     "position-queries": cmd_position_queries,
     "match-positions": cmd_match_positions, "standin-test": cmd_standin_test}[args.cmd](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
