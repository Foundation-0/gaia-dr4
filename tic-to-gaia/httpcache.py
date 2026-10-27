"""Polite, cached web requests.

Every response is saved on disk the first time it is fetched, in its own folder under
data/<kind>/<key>/. A second call with the same request reads the saved copy and sends
nothing. Every real request is also written to data/requests.log, so the traffic can be
counted afterwards.

Rules this module keeps:
  * one request at a time (the task allows at most two),
  * an identifying User-Agent,
  * at least MIN_GAP seconds between two requests to the same host,
  * after a temporary failure (a reset connection, a timeout, HTTP 502/503/504 and the like),
    wait and try again, at most RETRIES more times,
  * no log-in and no credentials.

Downloaded files are untrusted data. They are only read, never executed. Run code that
reads them with `python3 -I`.
"""

import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "Foundation0-gaia-dr4/0.1 (+https://github.com/Foundation-0/gaia-dr4)"
MIN_GAP = 1.0  # seconds between requests to one host
TIMEOUT = 300  # seconds to wait for one response (MAST needed 20 to 85 seconds per query)
RETRIES = 2  # extra tries after a temporary failure
RETRY_PAUSES = (10, 30)  # seconds to wait before the second and before the third try
# HTTP codes that mean "busy or restarting, try again later". Any other code (400 for a bad
# query, 404 and so on) is final and is not retried.
TRANSIENT_HTTP = (429, 500, 502, 503, 504)

_last_request_time = {}
_sleep = time.sleep  # the tests replace this so that they do not wait


class FetchError(RuntimeError):
    pass


def _key(method, url, data):
    blob = json.dumps([method, url, sorted(data.items()) if data else None])
    return hashlib.sha256(blob.encode()).hexdigest()[:20]


def _send_once(data_dir, kind, url, payload, method, key):
    """Send one request and write one line to requests.log.

    Returns (status, body, error text or None, error is temporary, start time).
    """
    host = urllib.parse.urlsplit(url).netloc
    wait = MIN_GAP - (time.time() - _last_request_time.get(host, 0))
    if wait > 0:
        _sleep(wait)
    req = urllib.request.Request(url, data=payload, method=method,
                                 headers={"User-Agent": USER_AGENT})
    started = time.time()
    status = None
    body = b""
    err = None
    temporary = False
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            status = resp.status
            body = resp.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read()
        err = "HTTP %d" % exc.code
        temporary = exc.code in TRANSIENT_HTTP
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        err = "%s: %s" % (type(exc).__name__, exc)
        temporary = True
    finally:
        _last_request_time[host] = time.time()
        os.makedirs(data_dir, exist_ok=True)
        with open(os.path.join(data_dir, "requests.log"), "a") as log:
            log.write(json.dumps({
                "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
                "kind": kind, "method": method, "url": url, "status": status,
                "bytes": len(body), "seconds": round(time.time() - started, 2),
                "error": err, "key": key}) + "\n")
    return status, body, err, temporary, started


def fetch(data_dir, kind, url, data=None, method=None, offline=False, reject=None):
    """Return (body bytes, info dict). `data` is a dict sent as a form POST body.

    The info dict has: url, status, from_cache, folder.
    With offline=True a missing cache entry raises FetchError instead of fetching.
    `reject`, if given, is called with the new body. If it returns a message, nothing is
    saved and FetchError is raised, so a bad answer is never served from the cache later.
    A temporary failure is tried again up to RETRIES times, with a pause that grows.
    """
    method = method or ("POST" if data else "GET")
    key = _key(method, url, data)
    folder = os.path.join(data_dir, kind, key)
    body_path = os.path.join(folder, "response.bin")
    meta_path = os.path.join(folder, "request.json")
    if os.path.exists(body_path) and os.path.exists(meta_path):
        with open(body_path, "rb") as fh:
            body = fh.read()
        with open(meta_path) as fh:
            meta = json.load(fh)
        return body, {"url": url, "status": meta["status"], "from_cache": True,
                      "folder": folder}
    if offline:
        raise FetchError("not in cache and offline mode is on: %s %s" % (method, url))

    payload = urllib.parse.urlencode(data).encode() if data else None
    for attempt in range(RETRIES + 1):
        status, body, err, temporary, started = _send_once(
            data_dir, kind, url, payload, method, key)
        if not err or not temporary or attempt == RETRIES:
            break
        _sleep(RETRY_PAUSES[min(attempt, len(RETRY_PAUSES) - 1)])
    if err:
        # Do not cache failures: the next run should try again.
        raise FetchError("%s for %s %s" % (err, method, url))
    if reject is not None:
        problem = reject(body)
        if problem:
            raise FetchError("%s for %s %s" % (problem, method, url))
    os.makedirs(folder, exist_ok=True)
    with open(body_path, "wb") as fh:
        fh.write(body)
    with open(meta_path, "w") as fh:
        json.dump({"method": method, "url": url, "data": data, "status": status,
                   "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started))},
                  fh, indent=1)
    return body, {"url": url, "status": status, "from_cache": False, "folder": folder}
