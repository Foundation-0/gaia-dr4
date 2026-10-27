#!/usr/bin/env python3
"""Record exactly what the live Gaia DataLink service answers for DR3 epoch photometry.

This is the "what does the archive accept today" test. It sends a fixed list of
single requests, one at a time, 1.5 seconds apart, with no retries, and writes one
line of JSON per request to results/probe-<group>.jsonl:

  structure_single  one source, every DATA_STRUCTURE name, old and new
  structure_multi   three sources, the same names
  formats           one source, every FORMAT value
  params            ID spelling, RELEASE, VALID_DATA, BAND, bad values
  batch             1, 10, 50, 51, 100 and 200 IDs in one request (one shot each)
  failure           sources with no epoch photometry, IDs that do not exist, bad IDs

Raw answers (headers and body) are kept in data/probe/<name>.* and are not
committed. Re-running skips requests that are already on disk. Use --fresh to
send them again.

Usage:
  python3 probe.py structure_single structure_multi formats params
"""
import argparse
import gzip
import hashlib
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "https://gea.esac.esa.int/data-server/data"
USER_AGENT = "Foundation0-gaia-dr4/0.1 (+https://github.com/Foundation-0/gaia-dr4)"
RAW_DIR = os.path.join(HERE, "data", "probe")
OUT_DIR = os.path.join(HERE, "results")
PAUSE = 1.5


def read_sources():
    """First three 'regular' sources of the test list."""
    ids = []
    with open(os.path.join(HERE, "sources", "test_sources.csv")) as f:
        next(f)
        for line in f:
            role, sid = line.split(",")[:2]
            if role == "regular":
                ids.append(sid)
    return ids


def read_pool():
    with open(os.path.join(HERE, "sources", "pool200.txt")) as f:
        return [x.strip() for x in f if x.strip()]


def read_roles():
    """{role: [source_id, ...]} from the test list."""
    roles = {}
    with open(os.path.join(HERE, "sources", "test_sources.csv")) as f:
        next(f)
        for line in f:
            role, sid = line.split(",")[:2]
            roles.setdefault(role, []).append(sid)
    return roles


def groups(ids):
    one, three = ids[0], ",".join(ids[:3])
    base = {"RETRIEVAL_TYPE": "EPOCH_PHOTOMETRY", "RELEASE": "Gaia DR3"}

    def req(**kw):
        p = dict(base)
        p.update(kw)
        return {k: v for k, v in p.items() if v is not None}

    g = {}
    names = [("omitted", None), ("INDIVIDUAL", "INDIVIDUAL"), ("RAW", "RAW"),
             ("DATAMODEL_STANDARD", "DATAMODEL_STANDARD"), ("DATAMODEL_GAIA", "DATAMODEL_GAIA"),
             ("COMBINED", "COMBINED"), ("lowercase_datamodel_standard", "datamodel_standard"),
             ("bogus_FOO", "FOO")]
    g["structure_single"] = [("single_ds_" + n, req(ID=one, FORMAT="CSV", DATA_STRUCTURE=v)) for n, v in names]
    g["structure_multi"] = [("multi3_ds_" + n, req(ID=three, FORMAT="CSV", DATA_STRUCTURE=v))
                            for n, v in names[:5]]
    ds = "DATAMODEL_STANDARD"
    g["formats"] = [("fmt_" + f, req(ID=one, FORMAT=f, DATA_STRUCTURE=ds))
                    for f in ("VOTABLE", "VOTABLE_PLAIN", "FITS", "ECSV", "XYZ")]
    g["params"] = [
        ("par_designation_no_release", req(ID="Gaia DR3 " + one, RELEASE=None, FORMAT="CSV", DATA_STRUCTURE=ds)),
        ("par_source_id_no_release", req(ID=one, RELEASE=None, FORMAT="CSV", DATA_STRUCTURE=ds)),
        ("par_release_DR2_on_DR3_id", req(ID=one, RELEASE="Gaia DR2", FORMAT="CSV", DATA_STRUCTURE=ds)),
        ("par_release_DR4", req(ID=one, RELEASE="Gaia DR4", FORMAT="CSV", DATA_STRUCTURE=ds)),
        ("par_valid_data_true", req(ID=one, FORMAT="CSV", DATA_STRUCTURE=ds, VALID_DATA="TRUE")),
        ("par_band_G_deprecated", req(ID=one, FORMAT="CSV", DATA_STRUCTURE=ds, BAND="G")),
        ("par_no_retrieval_type", req(ID=one, RETRIEVAL_TYPE=None, FORMAT="CSV", DATA_STRUCTURE=ds)),
    ]
    pool = read_pool()
    ds = "DATAMODEL_STANDARD"
    # Disjoint slices first, then the larger slices that overlap them.
    slices = [("n001_a", pool[0:1]), ("n010_a", pool[1:11]), ("n050_a", pool[11:61]),
              ("n051_a", pool[61:112]), ("n100_a", pool[0:100]), ("n200_a", pool[0:200]),
              ("n010_b", pool[61:71]), ("n050_b", pool[100:150])]
    roles = read_roles()
    reg, noep, fake = roles["regular"], roles["no_epoch"], roles["not_found"]
    g["failure"] = [
        ("fail_no_epoch_single", req(ID=noep[0], FORMAT="CSV", DATA_STRUCTURE=ds)),
        ("fail_not_found_single", req(ID=fake[0], FORMAT="CSV", DATA_STRUCTURE=ds)),
        ("fail_mixed_2ok_1noepoch", req(ID=",".join([reg[0], noep[0], reg[1]]), FORMAT="CSV", DATA_STRUCTURE=ds)),
        ("fail_mixed_2ok_1fake", req(ID=",".join([reg[0], fake[0], reg[1]]), FORMAT="CSV", DATA_STRUCTURE=ds)),
        ("fail_none_have_data_3", req(ID=",".join([noep[1], noep[2], fake[1]]), FORMAT="CSV", DATA_STRUCTURE=ds)),
        ("fail_malformed_id_letters", req(ID="12abc", FORMAT="CSV", DATA_STRUCTURE=ds)),
        ("fail_mixed_2ok_1noepoch_GAIA", req(ID=",".join([reg[0], noep[0], reg[1]]), FORMAT="CSV", DATA_STRUCTURE="DATAMODEL_GAIA")),
    ]
    g["batch"] = [("batch_" + n, req(ID=",".join(x), FORMAT="CSV", DATA_STRUCTURE=ds)) for n, x in slices]
    return g


def url_for(params):
    from urllib.parse import urlencode, quote_plus
    return BASE + "?" + urlencode(params, quote_via=quote_plus)


def clean_error_page(txt):
    """Plain text of an HTML error page, with the caller's address and session removed."""
    import html as _h
    import re
    txt = re.sub(r"(?is)<style.*?</style>", "", txt)
    txt = re.sub(r"\s+", " ", _h.unescape(re.sub(r"<[^>]+>", " ", txt))).strip()
    txt = re.sub(r"ip='[^']*'", "ip='<removed>'", txt)
    txt = re.sub(r"session='[^']*'", "session='<removed>'", txt)
    txt = re.sub(r"(Reqid: anonymous-)[0-9a-f-]+", r"\1<id>", txt)
    return txt


def describe(body):
    """Short, safe description of a response body (never executes anything)."""
    d = {"sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}
    if body[:2] == b"PK":
        d["kind"] = "zip"
        try:
            with zipfile.ZipFile(io.BytesIO(body)) as z:
                infos = z.infolist()
                d["n_members"] = len(infos)
                d["members_first3"] = [(i.filename, i.file_size) for i in infos[:3]]
                rows = 0
                for i in infos:
                    rows += max(z.read(i).count(b"\n") - 1, 0)  # CSV: lines minus the header
                d["rows_total"] = rows
                d["first_member_head"] = z.read(infos[0])[:200].decode("utf-8", "replace")
        except Exception as e:
            d["zip_error"] = str(e)
    elif body[:2] == b"\x1f\x8b":
        d["kind"] = "gzip"
        try:
            inner = gzip.decompress(body)
            d["inner_bytes"] = len(inner)
            d["inner_head"] = inner[:260].decode("utf-8", "replace")
            d["inner_is_tar"] = inner[257:262] == b"ustar"
        except Exception as e:
            d["gzip_error"] = str(e)
    elif body[:6] == b"SIMPLE":
        d["kind"] = "fits"
        d["head"] = body[:120].decode("ascii", "replace")
    else:
        d["kind"] = "text"
        txt = body.decode("utf-8", "replace")
        if txt.lstrip()[:5].lower() == "<html":
            d["kind"] = "html_error_page"
            d["message"] = clean_error_page(txt)[:600]
        else:
            d["head"] = txt[:320]
            d["lines"] = txt.count("\n")
            d["votable_rows"] = txt.count("<TR>")
    return d


def one_request(name, params):
    url = url_for(params)
    prefix = os.path.join(RAW_DIR, name)
    t0 = time.time()
    status, headers, body, err = None, {}, b"", None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
        with urllib.request.urlopen(req, timeout=120) as r:
            status, headers, body = r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        status, headers, body = e.code, dict(e.headers), e.read()
    except Exception as e:  # network trouble: record it, do not retry
        err = "%s: %s" % (type(e).__name__, e)
    elapsed = time.time() - t0
    keep = ("Content-Type", "Content-Disposition", "Content-Length", "Retry-After", "Transfer-Encoding", "Content-Encoding")
    rec = {
        "name": name,
        "when_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t0)),
        "url": url,
        "status": status,
        "seconds": round(elapsed, 2),
        "headers": {k: headers[k] for k in keep if k in headers},
        "error": err,
    }
    rec.update(describe(body))
    with open(prefix + ".body", "wb") as f:
        f.write(body)
    with open(prefix + ".json", "w") as f:
        json.dump(rec, f, indent=1)
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("groups", nargs="+")
    ap.add_argument("--fresh", action="store_true", help="send requests again even if saved")
    a = ap.parse_args()
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    table = groups(read_sources())
    for gname in a.groups:
        if gname not in table:
            sys.exit("unknown group %s; choose from %s" % (gname, ", ".join(table)))
        recs = []
        for name, params in table[gname]:
            saved = os.path.join(RAW_DIR, name + ".json")
            if os.path.exists(saved) and not a.fresh:
                with open(saved) as f:
                    rec = json.load(f)
            else:
                rec = one_request(name, params)
                time.sleep(PAUSE)
            recs.append(rec)
            print("%-34s %s %6.2fs %8s bytes  %s" % (name, rec["status"], rec["seconds"], rec["bytes"],
                                                     rec["headers"].get("Content-Type", rec["error"])))
        with open(os.path.join(OUT_DIR, "probe-%s.jsonl" % gname), "w") as f:
            for rec in recs:
                f.write(json.dumps(rec) + "\n")


if __name__ == "__main__":
    main()
