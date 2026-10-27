"""Run the DR3 stand-in queries on the live Gaia archive (anonymous, synchronous) and log what they return.

    python3 -I run_dr3_checks.py            # run each stand-in; answers are cached, so a re-run costs nothing
    python3 -I run_dr3_checks.py --verify   # ask the archive again (no cache) and compare with the first answer

Rows queries are run twice: once with TOP 20 (a few rows, saved in results/out/ and committed) and once in
full (saved under data/full/, not committed, because the file is large). Count and summary queries run once.
Templates (eb_by_source_ids, pt_by_source_ids, flags_in_cone) get their @...@ words filled from the rows
of the earlier queries.

Every run adds a line to results/run_log.tsv. build_queries.py reads that file to write the
"last ran without error" line of each query header.
"""
import csv
import hashlib
import io
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RUN_LOG = os.path.join(HERE, "results", "run_log.tsv")
OUT = os.path.join(HERE, "results", "out")
FULL = os.path.join(HERE, "data", "full")
TOP = 20
MAXREC = 100000   # ask for more rows than the archive's default limit of a synchronous query

SANITY = {
    "sanity_eb_reference_time_range":
        "SELECT MIN(reference_time) AS min_reference_time, MAX(reference_time) AS max_reference_time, "
        "MIN(frequency) AS min_frequency, MAX(frequency) AS max_frequency FROM gaiadr3.vari_eclipsing_binary",
    "sanity_eb_model_types":
        "SELECT model_type, COUNT(*) AS n_sources FROM gaiadr3.vari_eclipsing_binary GROUP BY model_type ORDER BY model_type",
    "sanity_pt_reference_time_range":
        "SELECT MIN(transit_reference_time) AS min_t0, MAX(transit_reference_time) AS max_t0, "
        "MIN(transit_period) AS min_period, MAX(transit_period) AS max_period FROM gaiadr3.vari_planetary_transit",
    "sanity_pt_copies_differ":
        "SELECT COUNT(*) AS n_rows_that_differ FROM gaiadr3.vari_planetary_transit AS a "
        "JOIN gaiadr3.vari_planetary_transit_13june2022 AS b ON a.source_id = b.source_id "
        "WHERE a.transit_period <> b.transit_period OR a.transit_reference_time <> b.transit_reference_time",
}


def log(query, variant, status, n_rows, value, seconds, digest, note=""):
    os.makedirs(os.path.dirname(RUN_LOG), exist_ok=True)
    new = not os.path.exists(RUN_LOG)
    with open(RUN_LOG, "a", encoding="utf-8") as f:
        if new:
            f.write("utc_time\tquery\tvariant\tstatus\tn_rows\tvalue\tseconds\tanswer_sha256\tnote\n")
        f.write("\t".join([time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), query, variant, status,
                           str(n_rows), value, "%.1f" % seconds, digest, note.replace("\t", " ")]) + "\n")


def run(adql, refresh=False, note=""):
    """Run one query. Returns (answer text, header, rows, seconds)."""
    data = {"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": adql, "MAXREC": str(MAXREC)}
    t0 = time.time()
    raw = common.fetch(common.TAP_SYNC, data=data, kind="TAP", note=note, refresh=refresh)
    seconds = time.time() - t0
    text = raw.decode("utf-8", errors="replace")
    if text.lstrip().startswith("<"):
        raise RuntimeError("the archive answered with XML: " + text[:300])
    rows = list(csv.reader(io.StringIO(text)))
    return text, rows[0], rows[1:], seconds


def fill(adql, name, ctx):
    if name == "eb_by_source_ids":
        return adql.replace("@SOURCE_IDS@", ", ".join(ctx["eb_ids"]))
    if name == "pt_by_source_ids":
        return adql.replace("@SOURCE_IDS@", ", ".join(ctx["pt_ids"]))
    if name == "flags_in_cone":
        ra, dec = ctx["cone"]
        return (adql.replace("@RA@", ra).replace("@DEC@", dec).replace("@RADIUS_DEG@", "0.0175"))
    return adql


def write_out(name, text, folder=OUT, suffix=""):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, name + suffix + ".csv"), "w", encoding="utf-8", newline="") as f:
        f.write(text)


def names_in_order():
    sys.path.insert(0, HERE)
    import build_queries
    return list(build_queries.Q.items())


def main(verify=False):
    ctx = {}
    ok = True
    items = names_in_order()
    jobs = [(n, q["kind"], os.path.join(HERE, "dr3", n + ".adql")) for n, q in items]
    for name, kind, path in jobs:
        adql = fill(common.read_adql(path), name, ctx)
        variants = [("full", adql)]
        if kind == "rows":
            variants = [("top%d" % TOP, re.sub(r"^SELECT\b", "SELECT TOP %d" % TOP, adql, count=1)), ("full", adql)]
        for variant, text_q in variants:
            try:
                answer, header, rows, secs = run(text_q, note="%s %s" % (name, variant))
                digest = hashlib.sha256(answer.encode()).hexdigest()[:16]
                value = rows[0][0] if (kind == "count" and rows) else ""
                if variant == "full" and kind == "rows":
                    write_out(name, answer, folder=FULL)
                else:
                    write_out(name, answer, suffix="_top%d" % TOP if variant != "full" else "")
                if verify:
                    answer2, _, rows2, secs2 = run(text_q, refresh=True, note="%s %s verify" % (name, variant))
                    same = answer2 == answer
                    log(name, "verify-" + variant, "ok" if same else "mismatch", len(rows2), value, secs2,
                        hashlib.sha256(answer2.encode()).hexdigest()[:16],
                        "same answer as before" if same else "ANSWER CHANGED")
                    ok = ok and same
                    print("%-36s %-6s verify: %s (%d rows)" % (name, variant, "same" if same else "CHANGED", len(rows2)))
                else:
                    log(name, variant, "ok", len(rows), value, secs, digest, "answer read from the disk cache" if secs < 0.05 else "")
                    print("%-36s %-6s %6d rows %6.1fs %s" % (name, variant, len(rows), secs, value))
                if name == "eb_long_period" and variant.startswith("top"):
                    ci = header.index("source_id")
                    ctx["eb_ids"] = [r[ci] for r in rows[:5]]
                    ctx["cone"] = (rows[0][header.index("ra")], rows[0][header.index("dec")])
                if name == "pt_candidates" and variant.startswith("top"):
                    ctx["pt_ids"] = [r[header.index("source_id")] for r in rows[:5]]
            except Exception as e:  # keep going so that one failure does not hide the others
                ok = False
                log(name, variant, "error", 0, "", 0.0, "", str(e)[:200])
                print("%-36s %-6s ERROR %s" % (name, variant, str(e)[:300]))
    if not verify:
        for name, q in SANITY.items():
            try:
                answer, header, rows, secs = run(q, note=name)
                write_out(name, answer)
                log(name, "full", "ok", len(rows), rows[0][0] if rows else "", secs, hashlib.sha256(answer.encode()).hexdigest()[:16])
                print("%-36s %s" % (name, rows[:6]))
            except Exception as e:
                ok = False
                log(name, "full", "error", 0, "", 0.0, "", str(e)[:200])
                print(name, "ERROR", str(e)[:300])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(verify="--verify" in sys.argv))
