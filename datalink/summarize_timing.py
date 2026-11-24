#!/usr/bin/env python3
"""Make the timing tables of the DR3 test from the logs under data/.

Inputs: the eleven fetch runs named in RUNS (data/<name>/events.jsonl) and the probe answers
(data/probe/*.json). README.md, section "Timing runs", gives the command for each folder.

Outputs, all in results/:
  requests.csv        one line per request that returned data (probe answers and fetch runs)
  fetch-runs.jsonl    the start and end line of every fetch run in RUNS, with its folder name
  timing-summary.txt  the tables printed by this script

Nothing is written unless every input is there and the tables can be made. The outputs are
written to new files first and then moved into place.

Usage:  python3 -I summarize_timing.py
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
RESULTS = os.path.join(HERE, "results")
# The fetch runs behind the tables (folder names under data/). Three of them are failure-path runs
# (a wrong release, and two runs with a time-out of 0.3 s). Their start and end lines are kept too.
RUNS = ("final_gaia", "final_std", "run40_b10_j1", "run40_b10_j2", "run40_b20_j2", "run_dr4_probe",
        "run_gaia_j2", "run_std_j1", "run_std_j2", "run_timeout_probe", "run_timeout_probe2")


def events_of(run):
    with open(os.path.join(DATA, run, "events.jsonl")) as f:
        return [json.loads(line) for line in f]


def missing_inputs():
    out = [r for r in sorted(RUNS) if not os.path.exists(os.path.join(DATA, r, "events.jsonl"))]
    if not glob.glob(os.path.join(DATA, "probe", "*.json")):
        out.append("probe")
    return out


def rows_in_body(path):
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
        ctype = r["headers"].get("Content-Type", "")
        if r["status"] != 200 or ctype not in ("text/csv", "application/zip"):
            continue  # only CSV answers, so that rows can be counted
        if "DATAMODEL_GAIA" in r["url"] or r["bytes"] == 0:
            continue  # one row per source, not comparable; or an empty answer
        id_param = urllib.parse.parse_qs(urllib.parse.urlsplit(r["url"]).query).get("ID", [""])[0]
        ids = [x.split()[-1] for x in id_param.split(",")]  # 'Gaia DR3 123' -> '123'
        rows = rows_in_body(js[:-5] + ".body")
        out.append({"run": "probe:" + r["name"], "jobs": 1, "n_ids": len(ids), "rows": rows, "bytes": r["bytes"],
                    "seconds": r["seconds"], "http_status": r["status"], "ids": ids})
    return out


def fetch_requests():
    out = []
    for run in sorted(RUNS):
        if "gaia" in run:
            continue  # DATAMODEL_GAIA: one row per source
        events = events_of(run)
        rows_of = {e["source_id"]: e["rows"] for e in events if e["event"] == "source" and e["status"] == "ok"}
        jobs = next(e["jobs"] for e in events if e["event"] == "run_start")
        for e in events:
            if e["event"] == "request" and e["http_status"] == 200:
                out.append({"run": run, "jobs": jobs, "n_ids": len(e["ids"]),
                            "rows": sum(rows_of.get(i, 0) for i in e["ids"]), "bytes": e["bytes"],
                            "seconds": e["seconds"], "http_status": 200, "ids": e["ids"]})
    return out


def fetch_run_lines():
    """results/fetch-runs.jsonl: the start and end line of every fetch run, with the run's folder name."""
    lines = []
    for run in sorted(RUNS):
        for e in events_of(run):
            if e["event"] in ("run_start", "run_end"):
                e["run"] = run
                lines.append(json.dumps(e, sort_keys=True) + "\n")
    return "".join(lines)


def empty_answer_seconds():
    """Seconds taken by requests that came back with status 200 and no content (no epoch photometry)."""
    out = []
    for js in sorted(glob.glob(os.path.join(DATA, "probe", "*.json"))):
        with open(js) as f:
            r = json.load(f)
        if r["status"] == 200 and r["bytes"] == 0:
            out.append(r["seconds"])
    for run in sorted(RUNS):
        for e in events_of(run):
            if e["event"] == "request" and e["http_status"] == 200 and e["bytes"] == 0:
                out.append(e["seconds"])
    return out


def whole_runs():
    """One line per complete fetch run of the 25 or 40 stand-in sources: wall-clock time and speed."""
    out = []
    for run in sorted(RUNS):
        start = end = None
        for e in events_of(run):
            if e["event"] == "run_start" and start is None:
                start = e
            if e["event"] == "run_end" and e["requests"] > 0 and end is None and start is not None:
                end = e
        if start and end and end["sources_asked"] in (25, 40) and not end["stopped_because"]:
            out.append((run, start["structure"], start["jobs"], start["batch_size"], end["sources_asked"],
                        end["ok"], end["requests"], end["seconds"]))
    return out


def paired_batches(rows):
    """The same 10-ID batches run with one job and with two (run40_b10_j1 and run40_b10_j2), answers with data."""
    def by_ids(run):
        return {tuple(r["ids"]): r["seconds"] for r in rows if r["run"] == run and r["rows"] > 0}
    one, two = by_ids("run40_b10_j1"), by_ids("run40_b10_j2")
    return [(k, one[k], two[k]) for k in one if k in two]


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
    total_ids = sum(r["n_ids"] for r in with_data)
    say("Rows per ID in these answers: mean %.1f (%d rows, %d IDs)" % (total_rows / total_ids, total_rows, total_ids))
    distinct = {i for r in with_data for i in r["ids"]}
    say("Different IDs among these requests: %d (the same IDs were asked for in several runs)" % len(distinct))

    empty = empty_answer_seconds()
    say("")
    say("Requests that came back empty (no epoch photometry): %d, median %.2f s, range %.2f to %.2f s" % (
        len(empty), statistics.median(empty), min(empty), max(empty)))

    pairs = paired_batches(rows)
    say("")
    say("The same 10-ID batches with one job and with two (run40_b10_j1, run40_b10_j2, answers with data):")
    for ids_, s1, s2 in pairs:
        say("  %5.1f s with 1 job, %5.1f s with 2 jobs: %+5.1f %%" % (s1, s2, 100 * (s2 / s1 - 1)))
    if pairs:
        change = [100 * (s2 / s1 - 1) for _, s1, s2 in pairs]
        say("  median change %+.1f %%, range %+.1f %% to %+.1f %%" % (
            statistics.median(change), min(change), max(change)))

    say("")
    say("Whole runs (wall-clock seconds, including pauses and the second look for missing sources):")
    say("%-18s %-19s %4s %6s %7s %4s %9s %8s %11s" % ("run", "structure", "jobs", "batch", "sources", "ok", "requests", "seconds", "sources/min"))
    for run, structure, jobs, batch, asked, ok, reqs, secs in whole_runs():
        say("%-18s %-19s %4d %6d %7d %4d %9d %8.1f %11.1f" % (run, structure, jobs, batch, asked, ok, reqs, secs, 60.0 * asked / secs))


def main():
    missing = missing_inputs()
    if missing:
        sys.exit("missing under data/: %s. Make them with the commands in README.md (section 'Timing runs'). "
                 "Nothing was written." % ", ".join(missing))
    rows = probe_requests() + fetch_requests()
    if not any(r["rows"] > 0 for r in rows):
        sys.exit("no request with data was found in the inputs. Nothing was written.")

    csv_buf = io.StringIO()
    w = csv.DictWriter(csv_buf, fieldnames=["run", "jobs", "n_ids", "rows", "bytes", "seconds", "http_status"],
                       extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    lines = []
    report(rows, lines.append)
    text = "\n".join(lines) + "\n"
    run_lines = fetch_run_lines()

    outputs = {
        os.path.join(RESULTS, "requests.csv"): csv_buf.getvalue(),
        os.path.join(RESULTS, "fetch-runs.jsonl"): run_lines,
        os.path.join(RESULTS, "timing-summary.txt"): text,
    }
    for path, content in outputs.items():  # all the work is done; now write
        with open(path + ".new", "w", newline="") as f:
            f.write(content)
    for path in outputs:
        os.replace(path + ".new", path)
    print("%d requests written to results/requests.csv, %d run lines to results/fetch-runs.jsonl"
          % (len(rows), run_lines.count("\n")))
    print()
    sys.stdout.write(text)


if __name__ == "__main__":
    main()
