#!/usr/bin/env python3
"""Collect the timing of every DataLink request made during the DR3 test into results/requests.csv.

Reads the one-shot probe answers (data/probe/*.json) and the logs of the fetch runs
(data/run*/ and data/final*/, file events.jsonl), and prints what they say about time per
request and rows per second. It needs the folders under data/ that the test made, so it
only works after the test has been run. Three files in results/ are the committed copy of
its output: requests.csv (one line per request that returned data), fetch-runs.jsonl (the
start and end line of every run) and timing-summary.txt (the tables printed here).

Usage:  python3 summarize_timing.py
"""
import csv
import glob
import io
import json
import os
import statistics
import sys
import urllib.parse
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
OUT = os.path.join(HERE, "results", "requests.csv")
RUN_FOLDERS = ("run*", "final*")


def run_event_files():
    out = []
    for pattern in RUN_FOLDERS:
        out += glob.glob(os.path.join(DATA, pattern, "events.jsonl"))
    return sorted(out)


def rows_in_body(path, ctype):
    """Data rows in a saved CSV or zip-of-CSV answer."""
    with open(path, "rb") as f:
        body = f.read()
    if not body:
        return 0
    if body[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            return sum(max(z.read(i).count(b"\n") - 1, 0) for i in z.infolist())
    return max(body.count(b"\n") - 1, 0)


def probe_requests():
    out = []
    for js in sorted(glob.glob(os.path.join(DATA, "probe", "*.json"))):
        with open(js) as f:
            r = json.load(f)
        name = r["name"]
        ctype = r["headers"].get("Content-Type", "")
        if r["status"] != 200 or ctype not in ("text/csv", "application/zip"):
            continue  # only CSV answers, so that rows can be counted
        if "DATAMODEL_GAIA" in r["url"] or r["bytes"] == 0:
            continue  # one row per source, not comparable; or an empty answer
        id_param = urllib.parse.parse_qs(urllib.parse.urlsplit(r["url"]).query).get("ID", [""])[0]
        ids = id_param.count(",") + 1
        rows = rows_in_body(js[:-5] + ".body", ctype)
        out.append({"run": "probe:" + name, "jobs": 1, "n_ids": ids, "rows": rows, "bytes": r["bytes"],
                    "seconds": r["seconds"], "http_status": r["status"]})
    return out


def fetch_requests():
    out = []
    for ev in run_event_files():
        run = os.path.basename(os.path.dirname(ev))
        if "gaia" in run:
            continue  # DATAMODEL_GAIA: one row per source
        events = []
        with open(ev) as f:
            for line in f:
                events.append(json.loads(line))
        rows_of = {e["source_id"]: e["rows"] for e in events if e["event"] == "source" and e["status"] == "ok"}
        jobs = next(e["jobs"] for e in events if e["event"] == "run_start")
        for e in events:
            if e["event"] == "request" and e["http_status"] == 200:
                out.append({"run": run, "jobs": jobs, "n_ids": len(e["ids"]),
                            "rows": sum(rows_of.get(i, 0) for i in e["ids"]), "bytes": e["bytes"],
                            "seconds": e["seconds"], "http_status": 200})
    return out


def write_run_summaries():
    """results/fetch-runs.jsonl: the start and end line of every fetch run, with the run's folder name."""
    path = os.path.join(HERE, "results", "fetch-runs.jsonl")
    n = 0
    with open(path, "w") as out:
        for ev in run_event_files():
            run = os.path.basename(os.path.dirname(ev))
            with open(ev) as f:
                for line in f:
                    e = json.loads(line)
                    if e["event"] in ("run_start", "run_end"):
                        e["run"] = run
                        out.write(json.dumps(e, sort_keys=True) + "\n")
                        n += 1
    print("%d run start/end lines written to results/fetch-runs.jsonl" % n)


def empty_answer_seconds():
    """Seconds taken by requests that came back with status 200 and no content (no epoch photometry)."""
    out = []
    for js in sorted(glob.glob(os.path.join(DATA, "probe", "*.json"))):
        with open(js) as f:
            r = json.load(f)
        if r["status"] == 200 and r["bytes"] == 0:
            out.append(r["seconds"])
    for ev in run_event_files():
        with open(ev) as f:
            for line in f:
                e = json.loads(line)
                if e["event"] == "request" and e["http_status"] == 200 and e["bytes"] == 0:
                    out.append(e["seconds"])
    return out


def whole_runs():
    """One line per complete fetch run of the 25 or 40 stand-in sources: wall-clock time and speed."""
    out = []
    for ev in run_event_files():
        run = os.path.basename(os.path.dirname(ev))
        start = end = None
        with open(ev) as f:
            for line in f:
                e = json.loads(line)
                if e["event"] == "run_start" and start is None:
                    start = e
                if e["event"] == "run_end" and e["requests"] > 0 and end is None and start is not None:
                    end = e
        if start and end and end["sources_asked"] in (25, 40) and not end["stopped_because"]:
            out.append((run, start["structure"], start["jobs"], start["batch_size"], end["sources_asked"],
                        end["ok"], end["requests"], end["seconds"]))
    return out


def r_squared(xs, ys):
    """How much of the variation in ys a straight line against xs explains (1.0 is a perfect line)."""
    slope, intercept = statistics.linear_regression(xs, ys)
    mean = statistics.fmean(ys)
    miss = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    return 1 - miss / sum((y - mean) ** 2 for y in ys)


def report(rows, say):
    with_data = [r for r in rows if r["rows"] > 0]
    say("By number of IDs in the request (answers with data only):")
    say("%6s %4s %10s %12s %12s %10s" % ("n_ids", "n", "sec_median", "sec_min-max", "rows_median", "rows/s"))
    for n in sorted({r["n_ids"] for r in with_data}):
        g = [r for r in with_data if r["n_ids"] == n]
        secs = [r["seconds"] for r in g]
        say("%6d %4d %10.1f %12s %12.0f %10.1f" % (
            n, len(g), statistics.median(secs), "%.1f-%.1f" % (min(secs), max(secs)),
            statistics.median(r["rows"] for r in g), sum(r["rows"] for r in g) / sum(secs)))

    xs = [r["rows"] for r in with_data]
    ys = [r["seconds"] for r in with_data]
    slope, intercept = statistics.linear_regression(xs, ys)
    say("")
    say("Line through all requests with data: seconds = %.2f + %.4f * rows  (%d requests, R squared %.3f)" % (
        intercept, slope, len(with_data), r_squared(xs, ys)))
    say("  so about %.1f rows per second once a request is running" % (1 / slope))
    ids = [r["n_ids"] for r in with_data]
    slope2, intercept2 = statistics.linear_regression(ids, ys)
    say("Line against number of IDs:          seconds = %.2f + %.2f * ids  (R squared %.3f)" % (
        intercept2, slope2, r_squared(ids, ys)))
    per_src = [r["seconds"] / r["n_ids"] for r in with_data if r["n_ids"] >= 10]
    say("Seconds per ID in requests of 10 or more: median %.2f, range %.2f to %.2f" % (
        statistics.median(per_src), min(per_src), max(per_src)))
    total_rows = sum(xs)
    say("Rows per ID in these answers: mean %.1f (%d rows, %d IDs)" % (
        total_rows / sum(r["n_ids"] for r in with_data), total_rows, sum(r["n_ids"] for r in with_data)))

    empty = empty_answer_seconds()
    say("")
    say("Requests that came back empty (no epoch photometry): %d, median %.2f s, range %.2f to %.2f s" % (
        len(empty), statistics.median(empty), min(empty), max(empty)))

    say("")
    say("Whole runs (wall-clock seconds, including pauses and the second look for missing sources):")
    say("%-18s %-19s %4s %6s %7s %4s %9s %8s %11s" % ("run", "structure", "jobs", "batch", "sources", "ok", "requests", "seconds", "sources/min"))
    for run, structure, jobs, batch, asked, ok, reqs, secs in whole_runs():
        say("%-18s %-19s %4d %6d %7d %4d %9d %8.1f %11.1f" % (run, structure, jobs, batch, asked, ok, reqs, secs, 60.0 * asked / secs))


def main():
    write_run_summaries()
    rows = probe_requests() + fetch_requests()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    cols = ["run", "jobs", "n_ids", "rows", "bytes", "seconds", "http_status"]
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print("%d requests written to %s" % (len(rows), os.path.relpath(OUT, HERE)))
    lines = []
    report(rows, lines.append)
    text = "\n".join(lines) + "\n"
    with open(os.path.join(HERE, "results", "timing-summary.txt"), "w") as f:
        f.write(text)
    print()
    sys.stdout.write(text)


if __name__ == "__main__":
    main()
