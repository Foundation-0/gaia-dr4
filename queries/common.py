"""Shared helpers: a polite, caching web client, a Gaia TAP client and a CSV reader.

Every network request goes through `fetch`. It
  * sends an identifying User-Agent,
  * waits at least MIN_GAP seconds between requests (one request at a time),
  * saves the answer on disk, so a repeated call never touches the network,
  * appends one line per network request to results/request_log.tsv.

Downloaded answers are untrusted data. They are only ever read as text or CSV
here, never executed.
"""
import csv
import hashlib
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "data", "cache")
LOG = os.path.join(HERE, "results", "request_log.tsv")
USER_AGENT = "Foundation0-gaia-dr4/0.1 (+https://github.com/Foundation-0/gaia-dr4)"
MIN_GAP = 1.0  # seconds between two network requests
TAP_SYNC = "https://gea.esac.esa.int/tap-server/tap/sync"

_last_request = [0.0]


def _log(kind, url, key, status, nbytes, note=""):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    new = not os.path.exists(LOG)
    with open(LOG, "a", encoding="utf-8") as f:
        if new:
            f.write("utc_time\tkind\tstatus\tbytes\tcache_key\turl\tnote\n")
        f.write("%s\t%s\t%s\t%s\t%s\t%s\t%s\n" % (
            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), kind, status,
            nbytes, key, url[:200], note.replace("\t", " ").replace("\n", " ")[:200]))


def _short_error(content):
    """Keep the useful part of an error page (the archive wraps messages in a VOTable)."""
    text = content.decode("utf-8", errors="replace")
    import re
    m = re.search(r'<INFO name="QUERY_STATUS" value="ERROR">(.*?)</INFO>', text, re.S)
    return (m.group(1) if m else text).strip()[:1500]


def fetch(url, data=None, kind="GET", note="", timeout=180, refresh=False):
    """Return the response body as bytes. `data` (dict) makes it a POST."""
    body = urllib.parse.urlencode(data).encode() if data else None
    key = hashlib.sha256((url + "\0" + (body.decode() if body else "")).encode()).hexdigest()[:24]
    folder = os.path.join(CACHE, key)
    path = os.path.join(folder, "response.bin")
    if os.path.exists(path) and not refresh:
        with open(path, "rb") as f:
            return f.read()
    wait = MIN_GAP - (time.time() - _last_request[0])
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            content = r.read()
            status = r.status
    except urllib.error.HTTPError as e:
        content = e.read()
        status = e.code
    except Exception as e:  # network trouble: log it and let the caller see it
        _last_request[0] = time.time()
        _log(kind, url, key, "ERR", 0, "%s: %s" % (type(e).__name__, e))
        raise
    _last_request[0] = time.time()
    _log(kind, url, key, status, len(content), note if status == 200 else note + " | " + _short_error(content)[:150])
    if status == 200:
        os.makedirs(folder, exist_ok=True)
        with open(path, "wb") as f:
            f.write(content)
        with open(os.path.join(folder, "meta.json"), "w") as f:
            json.dump({"url": url, "post": body.decode() if body else None,
                       "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                       "note": note}, f, indent=1)
    else:
        raise RuntimeError("HTTP %s from %s: %s" % (status, url, _short_error(content)))
    return content


def tap_query(adql, note="", maxrec=None, refresh=False):
    """Run one synchronous ADQL query on the Gaia archive, anonymously.
    Returns (header, rows) where rows are lists of strings."""
    data = {"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": adql}
    if maxrec:
        data["MAXREC"] = str(maxrec)
    raw = fetch(TAP_SYNC, data=data, kind="TAP", note=note, refresh=refresh)
    text = raw.decode("utf-8", errors="replace")
    if text.lstrip().startswith("<"):
        raise RuntimeError("TAP returned XML (probably an error): " + text[:500])
    rows = list(csv.reader(io.StringIO(text)))
    return rows[0], rows[1:]


def read_adql(path):
    """Read an .adql file and return the query text without comment lines."""
    with open(path, encoding="utf-8") as f:
        lines = [ln.rstrip("\n") for ln in f if not ln.lstrip().startswith("--")]
    return "\n".join(lines).strip() + "\n"


def one_line(adql):
    return " ".join(adql.split())


if __name__ == "__main__":
    sys.exit("This module is a library.")
