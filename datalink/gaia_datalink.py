#!/usr/bin/env python3
"""Fetch Gaia epoch photometry through the Gaia archive's DataLink service.

Epoch photometry is a star's brightness at each observation. In Gaia DR3 it
comes from DataLink, the archive's file service. In DR4 it will come only from
DataLink. This script takes a file of Gaia source IDs and saves one CSV file
per source, with checks and a log.

What it does, in plain terms:

* It asks for several sources per request (a "batch") and splits the answer
  into one file per source.
* It never has more than `--jobs` requests open at once. The limit cannot be
  set above 5, the archive's documented limit of jobs in execution per user.
  Several runs on one computer share the same limit through lock files.
* It waits between requests, and when a request fails it waits longer each
  time (exponential backoff). It obeys a Retry-After header.
* It checks every file (columns, number of rows, times, source ID) before it
  keeps it, and records a SHA-256 checksum.
* The archive leaves out a source that has no epoch photometry. Before it
  records "no data" the script asks once more for the sources that were
  missing (a "second look"), so that a dropped answer is not mistaken for
  a source without data. `--no-second-look` turns this off.
* It remembers what is done, so a run that stopped can be started again with
  the same command and carries on.
* It writes a log line for every request and every source.

Standard library only. Usage:

    python3 gaia_datalink.py fetch ids.txt --out run1
    python3 gaia_datalink.py check run1

See README.md for the details and for what was and was not tested.

This work has made use of data from the European Space Agency (ESA) mission
Gaia (https://www.cosmos.esa.int/gaia), processed by the Gaia Data Processing
and Analysis Consortium (DPAC,
https://www.cosmos.esa.int/web/gaia/dpac/consortium).
"""
import argparse
import collections
import concurrent.futures
import contextlib
import csv
import datetime
import email.utils
import getpass
import hashlib
import html
import http.client
import http.cookiejar
import io
import json
import logging
import os
import random
import re
import sys
import tarfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import zlib

try:  # lock files are used to share the job limit between processes
    import fcntl
except ImportError:  # Windows
    fcntl = None

VERSION = "0.1"
USER_AGENT = "Foundation0-gaia-dr4/%s (+https://github.com/Foundation-0/gaia-dr4)" % VERSION
DATA_URL = "https://gea.esac.esa.int/data-server/data"
LOGIN_URL = "https://gea.esac.esa.int/data-server/login"

# Limits from ESA's news item of 14 Oct 2026 and the archive user guide (quotas table).
MAX_JOBS = 5            # jobs in execution at once, per user
QUEUE_LIMIT = 50        # jobs waiting, per user
ANON_MAX_IDS = 50       # sources per DataLink request, anonymous. Seen on the live archive, 27 Oct 2026.
SIGNED_IN_MAX_IDS = 5000  # sources per DataLink request, signed in. From the user guide. NOT tested here.

STRUCTURES = ("DATAMODEL_STANDARD", "DATAMODEL_GAIA")
OLD_STRUCTURE_NAMES = {"INDIVIDUAL": "DATAMODEL_STANDARD", "RAW": "DATAMODEL_GAIA"}
FORMATS = ("CSV",)  # the only format this script validates. See README.md.
MAX_UNPACKED = 400_000_000  # bytes. A zip or gzip answer that unpacks to more than this is refused (a "bomb").


class FatalError(Exception):
    """The run cannot succeed (wrong parameter, no permission). Stop at once."""


class Aborted(Exception):
    """The run was stopped on purpose (request limit, service looks down, Ctrl-C)."""


class ValidationError(Exception):
    """A downloaded file failed a check."""


class TransportError(Exception):
    """The network failed (timeout, reset connection, cut-off answer)."""


# --------------------------------------------------------------------------
# What a good file looks like
# --------------------------------------------------------------------------

class Profile:
    """Checks for one data release.

    `columns` are the columns that must be present in a DATAMODEL_STANDARD file (more are allowed).
    `bands` lists (name, time column, magnitude column, flux column) for G, BP and RP.
    `gaia_columns` and `gaia_arrays` are the same for DATAMODEL_GAIA, or None if not known.
    `time_range` is in days since JD 2455197.5 (the epoch photometry time zero).
    `max_rows` is the largest number of epochs we call plausible.
    """

    def __init__(self, columns, bands, gaia_columns, gaia_arrays, time_range, max_rows, note):
        self.columns = columns
        self.bands = bands
        self.gaia_columns = gaia_columns
        self.gaia_arrays = gaia_arrays
        self.time_range = time_range
        self.max_rows = max_rows
        self.note = note


_DR3_COLUMNS = [
    "solution_id", "source_id", "transit_id", "g_transit_time", "g_transit_flux", "g_transit_flux_error",
    "g_transit_flux_over_error", "g_transit_mag", "bp_obs_time", "bp_flux", "bp_flux_error",
    "bp_flux_over_error", "bp_mag", "rp_obs_time", "rp_flux", "rp_flux_error", "rp_flux_over_error",
    "rp_mag", "variability_flag_g_reject", "variability_flag_bp_reject", "variability_flag_rp_reject",
    "g_other_flags", "bp_other_flags", "rp_other_flags", "rejected_by_photometry",
]
_DR3_GAIA_COLUMNS = [
    "solution_id", "source_id", "n_transits", "transit_id", "g_transit_time", "g_transit_flux",
    "g_transit_mag", "bp_obs_time", "bp_flux", "bp_mag", "rp_obs_time", "rp_flux", "rp_mag",
]
# Arrays in a DR3 DATAMODEL_GAIA row that must each have n_transits entries.
_DR3_GAIA_ARRAYS = ["transit_id", "g_transit_time", "g_transit_flux", "g_transit_mag",
                    "bp_obs_time", "bp_flux", "bp_mag", "rp_obs_time", "rp_flux", "rp_mag"]
_DR3_BANDS = (("g", "g_transit_time", "g_transit_mag", "g_transit_flux"),
              ("bp", "bp_obs_time", "bp_mag", "bp_flux"),
              ("rp", "rp_obs_time", "rp_mag", "rp_flux"))
# DR4: the G column names change in the draft data model of 26 Jun 2026 (g_obs_time, g_flux, g_mag).
_DR4_BANDS = (("g", "g_obs_time", "g_mag", "g_flux"),
              ("bp", "bp_obs_time", "bp_mag", "bp_flux"),
              ("rp", "rp_obs_time", "rp_mag", "rp_flux"))
_DR4_COLUMNS = ["source_id", "transit_id", "g_obs_time", "g_flux", "g_mag", "bp_obs_time", "bp_flux", "bp_mag",
                "rp_obs_time", "rp_flux", "rp_mag"]

PROFILES = {
    # Checked against the live archive on 27 Oct 2026 (25 columns, times 1703 to 2683 in 150 sources).
    "Gaia DR3": Profile(_DR3_COLUMNS, _DR3_BANDS, _DR3_GAIA_COLUMNS, _DR3_GAIA_ARRAYS, (1650.0, 2720.0), 3000,
                        "checked on the live archive, 27 Oct 2026"),
    # UNVERIFIED. Column names are from ESA's DRAFT DR4 data model (26 Jun 2026), which may change.
    # The DATAMODEL_STANDARD file may not use the same names as the draft. DR4 covers 25 Jul 2014 to
    # 20 Jan 2020, which is up to day 3671 after JD 2455197.5. The DATAMODEL_GAIA layout for DR4 is not
    # known, so it is refused for DR4.
    "Gaia DR4": Profile(_DR4_COLUMNS, _DR4_BANDS, None, None, (1650.0, 3700.0), 20000,
                        "UNVERIFIED: column names come from the draft data model of 26 Jun 2026"),
}


def _float(text, what):
    """Parse a number. Empty and NaN mean 'not measured' and give None."""
    t = text.strip()
    if t == "" or t.lower() in ("nan", "null", "none"):
        return None
    try:
        return float(t)
    except ValueError:
        raise ValidationError("%s is not a number: %r" % (what, t[:40]))


def _check_times_and_mags(get, nrows, profile, source_id):
    """Shared checks. `get(col, i)` returns the text of a column in row i, or None if no such column."""
    lo, hi = profile.time_range
    times = []
    counts = {}
    for band, tcol, mcol, fcol in profile.bands:
        n = 0
        for i in range(nrows):
            f = get(fcol, i)
            if f is not None:
                _float(f, fcol)  # must be a number, or empty when not measured
            t = get(tcol, i)
            if t is not None:
                tv = _float(t, tcol)
                if tv is not None:
                    n += 1
                    times.append(tv)
                    if not lo <= tv <= hi:
                        raise ValidationError("%s = %.3f is outside the plausible range %g to %g" % (tcol, tv, lo, hi))
            m = get(mcol, i)
            if m is not None:
                mv = _float(m, mcol)
                if mv is not None and not 0.0 < mv < 35.0:
                    raise ValidationError("%s = %.3f is not a plausible magnitude" % (mcol, mv))
        counts["n_" + band] = n
    if not times:
        raise ValidationError("no observation times at all")
    counts["t_first"] = round(min(times), 4)
    counts["t_last"] = round(max(times), 4)
    return counts


def read_csv_rows(text):
    """All rows of a CSV text. A file the csv module cannot read (for example a cell over 131,072
    characters) is a failed check, not a crash."""
    try:
        return list(csv.reader(io.StringIO(text, newline="")))
    except csv.Error as e:
        raise ValidationError("cannot read the file as CSV: %s" % e)


def check_standard_csv(data, source_id, profile):
    """Check one DATAMODEL_STANDARD CSV file (one source, one row per epoch). Returns facts about it."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValidationError("not UTF-8 text")
    if not text.endswith("\n"):
        raise ValidationError("file does not end with a newline (cut off?)")
    rows = read_csv_rows(text)
    header, body = rows[0], rows[1:]
    missing = [c for c in profile.columns if c not in header]
    if missing:
        raise ValidationError("missing columns: " + ", ".join(missing))
    ix = {c: i for i, c in enumerate(header)}
    if not body:
        raise ValidationError("no data rows")
    if len(body) > profile.max_rows:
        raise ValidationError("%d rows is more than the plausible maximum %d" % (len(body), profile.max_rows))
    for k, r in enumerate(body, start=2):
        if len(r) != len(header):
            raise ValidationError("line %d has %d fields, the header has %d" % (k, len(r), len(header)))
        if r[ix["source_id"]] != source_id:
            raise ValidationError("line %d is for source %s, not %s" % (k, r[ix["source_id"]], source_id))
    if "transit_id" in ix:
        ids = [r[ix["transit_id"]] for r in body if r[ix["transit_id"]] != ""]
        if len(ids) != len(set(ids)):
            raise ValidationError("transit_id repeats")
    info = _check_times_and_mags(lambda c, i: body[i][ix[c]] if c in ix else None, len(body), profile, source_id)
    info["rows"] = len(body)
    return info


def parse_array(cell):
    """'(a, b, c)' -> ['a', 'b', 'c']. The DATAMODEL_GAIA CSV writes each array into one cell."""
    s = cell.strip()
    if not (s.startswith("(") and s.endswith(")")):
        raise ValidationError("array cell does not look like (a, b, ...): %r" % s[:30])
    inner = s[1:-1].strip()
    return [] if inner == "" else [x.strip() for x in inner.split(",")]


def check_gaia_row(header, row, source_id, profile):
    """Check one DATAMODEL_GAIA row (one source, arrays in the cells)."""
    if profile.gaia_columns is None:
        raise ValidationError("the DATAMODEL_GAIA layout is not known for this release")
    missing = [c for c in profile.gaia_columns if c not in header]
    if missing:
        raise ValidationError("missing columns: " + ", ".join(missing))
    ix = {c: i for i, c in enumerate(header)}
    if len(row) != len(header):
        raise ValidationError("row has %d fields, the header has %d" % (len(row), len(header)))
    if row[ix["source_id"]] != source_id:
        raise ValidationError("row is for source %s, not %s" % (row[ix["source_id"]], source_id))
    try:
        n = int(row[ix["n_transits"]])
    except ValueError:
        raise ValidationError("n_transits is not an integer")
    if not 1 <= n <= profile.max_rows:
        raise ValidationError("n_transits = %d is not plausible" % n)
    arrays = {}
    for c in profile.gaia_arrays:
        if c in ix:
            arrays[c] = parse_array(row[ix[c]])
            if len(arrays[c]) != n:
                raise ValidationError("%s has %d entries, n_transits is %d" % (c, len(arrays[c]), n))
    info = _check_times_and_mags(lambda c, i: arrays[c][i] if c in arrays else None, n, profile, source_id)
    info["rows"] = n
    return info


# --------------------------------------------------------------------------
# Reading the archive's answers
# --------------------------------------------------------------------------

Response = collections.namedtuple("Response", "status headers body")
Outcome = collections.namedtuple("Outcome", "kind message retry_after limit", defaults=("", 0.0, 0))

# Messages that mean every request of this kind will fail, so retrying is pointless.
FATAL_PHRASES = (
    "data structure has been deprecated",
    "invalid data structure parameter",
    "no formatter has been found",
    "no services found for",
)


OWNER_BLOCK = "UwsJobOwner{"
# Fields that can name or locate a caller. They are removed wherever they appear, not only inside the owner block.
PERSONAL_FIELD = re.compile(r"\b(name|mail|authUsername|pseudo|authGroups|session|ip)="
                            r"(?:'[^']*'|\"[^\"]*\"|\[[^\]]*\]|[^\s,;)}\]]+)")


def _cut_owner_blocks(txt):
    """Replace each UwsJobOwner{...} block with a marker. Braces are counted, so a nested brace does not end
    the block early. A block with no closing brace (cut off) is removed to the end of the text."""
    out, i = [], 0
    while True:
        j = txt.find(OWNER_BLOCK, i)
        if j < 0:
            out.append(txt[i:])
            return "".join(out)
        out.append(txt[i:j] + "UwsJobOwner{<removed>}")
        depth, k = 1, j + len(OWNER_BLOCK)
        while k < len(txt) and depth:
            if txt[k] == "{":
                depth += 1
            elif txt[k] == "}":
                depth -= 1
            k += 1
        i = k


def scrub_personal(txt):
    """Remove what could name or locate the caller from an archive message.

    The archive's error pages carry a block `UwsJobOwner{id=..., name=..., mail=..., session=..., ip=...}`
    and a request ID `Reqid: <user>-<uuid>`. For anonymous users the values are 'null' or 'anonymous'.
    For a signed-in user they probably hold real values. Whether they do was NOT checked (no account was
    used). So the whole block is removed, and so is each personal field (name, mail, user name, groups,
    session, address) wherever it appears, the whole request ID, and any e-mail address.
    Checked on synthetic pages only (see test_gaia_datalink.py).
    """
    txt = _cut_owner_blocks(txt)
    txt = re.sub(r"Reqid: [^\s,;)\]}]+", "Reqid: <removed>", txt)
    txt = re.sub(r"(?i)\bfor user:? (?!UwsJobOwner)[^\s,;}]+", "for user: <removed>", txt)
    txt = PERSONAL_FIELD.sub(lambda m: m.group(1) + "=<removed>", txt)
    txt = re.sub(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", "<removed>", txt)
    return txt


def page_message(body):
    """The readable part of an archive error page, with the caller's name, address and session removed."""
    txt = body[:20000].decode("utf-8", "replace")
    if txt.lstrip()[:5].lower() == "<html":
        txt = re.sub(r"(?is)<style.*?</style>", "", txt)
        txt = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", txt))).strip()
        m = re.search(r"Message: (.*?) Cannot process request", txt)
        if m and m.group(1).strip():
            txt = m.group(1).strip()
    return scrub_personal(txt)[:400]


def parse_retry_after(value):
    """Retry-After is a number of seconds or an HTTP date. Returns seconds (0 if absent or unreadable)."""
    if not value:
        return 0.0
    value = value.strip()
    if re.fullmatch(r"\d+(\.\d+)?", value):
        return float(value)
    try:
        when = email.utils.parsedate_to_datetime(value)
        return max(0.0, (when - datetime.datetime.now(when.tzinfo)).total_seconds())
    except (TypeError, ValueError):
        return 0.0


def classify(resp):
    """Decide what an answer means. Kinds:

    data     a payload to check and save
    empty    status 200 and no content: the archive has no such product for these sources
    retry    a temporary problem (429, 5xx, a page where data should be): wait and try again
    queue    the archive says the job queue or job limit is full: wait longer
    too_many more IDs than allowed in one request (limit says how many)
    fatal    the request itself is wrong or not allowed: stop the run
    fail     this request cannot work (other 4xx)
    """
    s = resp.status
    ctype = resp.headers.get("content-type", "").lower()
    if s == 200:
        if not resp.body:
            return Outcome("empty")
        if "html" in ctype:
            return Outcome("retry", "an HTML page with status 200: " + page_message(resp.body))
        return Outcome("data")
    msg = page_message(resp.body)
    low = msg.lower()
    ra = parse_retry_after(resp.headers.get("retry-after"))
    m = re.search(r"maximum number of source ids reached \(max: (\d+)", low)
    if m:
        return Outcome("too_many", msg, 0.0, int(m.group(1)))
    if any(p in low for p in FATAL_PHRASES):
        return Outcome("fatal", msg)
    if s in (401, 403):
        return Outcome("fatal", "HTTP %d: %s" % (s, msg))
    if "queue" in low or "jobs in execution" in low or "too many jobs" in low or "maximum number of jobs" in low:
        return Outcome("queue", "HTTP %d: %s" % (s, msg), ra)
    if s == 429:
        return Outcome("retry", "HTTP 429 Too Many Requests " + msg, ra)
    if s in (408, 500, 502, 503, 504):
        return Outcome("retry", "HTTP %d: %s" % (s, msg), ra)
    if 400 <= s < 500:
        return Outcome("fail", "HTTP %d: %s" % (s, msg))
    return Outcome("retry", "unexpected HTTP status %d: %s" % (s, msg), ra)


def unpack_answer(body):
    """The files inside an answer, as [(name, bytes)].

    A zip gives its members. A gzip gives the file inside it, or the members of a tar archive inside it
    (ESA's user guide says several sources come as a .gzip. On 27 Oct 2026 the live archive sent a zip,
    so the gzip case has NOT been seen live). Anything else is one file with no name.
    Nothing is written to disk here, and a member's name is never used as a path.
    """
    if body[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(body)) as z:
                infos = [i for i in z.infolist() if not i.is_dir()]
                if sum(i.file_size for i in infos) > MAX_UNPACKED:
                    raise ValidationError("the zip unpacks to more than %d bytes" % MAX_UNPACKED)
                return [(i.filename, z.read(i)) for i in infos]  # z.read checks each member's CRC
        except zipfile.BadZipFile as e:
            raise ValidationError("bad zip file: %s" % e)
    if body[:2] == b"\x1f\x8b":
        unpacker = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            inner = unpacker.decompress(body, MAX_UNPACKED + 1)
        except zlib.error as e:
            raise ValidationError("bad gzip file: %s" % e)
        if len(inner) > MAX_UNPACKED:
            raise ValidationError("the gzip file unpacks to more than %d bytes" % MAX_UNPACKED)
        if not unpacker.eof:
            raise ValidationError("the gzip file is cut off")
        if inner[257:262] == b"ustar":
            try:
                with tarfile.open(fileobj=io.BytesIO(inner)) as tf:
                    return [(m.name, tf.extractfile(m).read()) for m in tf.getmembers() if m.isfile()]
            except tarfile.TarError as e:
                raise ValidationError("bad tar file: %s" % e)
        return [("", inner)]
    return [("", body)]


def split_standard(body, structure):
    """Split a payload into {source_id: bytes of that source's CSV}."""
    parts = {}
    for name, data in unpack_answer(body):  # several sources come as a zip with one CSV per source
        # Use the source_id inside the file. A file name that says otherwise is an error.
        sid = _first_source_id(data)
        if not sid:
            raise ValidationError("cannot read a source_id from %s" % (name or "the answer"))
        m = re.search(r"_(\d+)\.csv$", name)
        if m and m.group(1) != sid:
            raise ValidationError("%s holds source %s" % (name, sid))
        if sid in parts:
            raise ValidationError("source %s appears twice in the answer" % sid)
        parts[sid] = data
    return parts


def _first_source_id(data):
    """source_id of the first data row of a CSV file (bytes), or None."""
    try:
        rd = csv.reader(io.StringIO(data.decode("utf-8"), newline=""))
        header = next(rd)
        row = next(rd)
        return row[header.index("source_id")]
    except (UnicodeDecodeError, StopIteration, ValueError, IndexError, csv.Error):
        return None


def split_gaia(body):
    """DATAMODEL_GAIA: one CSV with one row per source. Returns (header, {source_id: row})."""
    members = unpack_answer(body)
    if len(members) != 1:
        raise ValidationError("expected one CSV file for DATAMODEL_GAIA, got %d files" % len(members))
    body = members[0][1]
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        raise ValidationError("not UTF-8 text")
    if not text.endswith("\n"):
        raise ValidationError("file does not end with a newline (cut off?)")
    rows = read_csv_rows(text)
    header = rows[0]
    if "source_id" not in header:
        raise ValidationError("no source_id column")
    k = header.index("source_id")
    out = {}
    for r in rows[1:]:
        if len(r) != len(header):
            raise ValidationError("a row has %d fields, the header has %d" % (len(r), len(header)))
        if r[k] in out:
            raise ValidationError("source %s appears twice" % r[k])
        out[r[k]] = r
    return header, out


# --------------------------------------------------------------------------
# Network
# --------------------------------------------------------------------------

class Transport:
    """Sends requests. Only this class touches the network, so tests can replace it."""

    def __init__(self, timeout=300.0):
        self.timeout = timeout
        self.jar = http.cookiejar.CookieJar()  # login cookie lives in memory only
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def _send(self, req):
        try:
            with self.opener.open(req, timeout=self.timeout) as r:
                return Response(r.status, {k.lower(): v for k, v in r.headers.items()}, r.read())
        except urllib.error.HTTPError as e:
            try:
                body = e.read()
            except (OSError, http.client.HTTPException):
                body = b""
            return Response(e.code, {k.lower(): v for k, v in e.headers.items()}, body)
        except (OSError, http.client.HTTPException) as e:  # includes timeouts, resets, IncompleteRead
            raise TransportError("%s: %s" % (type(e).__name__, e))

    def get(self, url):
        return self._send(urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"}))

    def post_form(self, url, fields):
        data = urllib.parse.urlencode(fields).encode()
        return self._send(urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT}))


def sign_in(transport, user, password, url=LOGIN_URL, allow_any_host=False):
    """Sign in with the documented login form. The cookie stays in memory.

    WRITTEN FROM THE DOCUMENTATION, NEVER RUN AGAINST THE REAL ARCHIVE (no account was
    used for this test). Credentials go only to an https address on esa.int.
    """
    host = urllib.parse.urlsplit(url)
    if not allow_any_host and not (host.scheme == "https" and (host.hostname or "").endswith(".esa.int")):
        raise FatalError("refusing to send credentials to %s" % url)
    resp = transport.post_form(url, {"username": user, "password": password})
    if resp.status >= 400:
        raise FatalError("sign-in failed with HTTP %d" % resp.status)


class SlotPool:
    """At most `n` requests open at once, in this process and in every process sharing `directory`.

    In a process the limit is a semaphore. Across processes it is a set of n lock files:
    a request must hold one of them while it is in flight.
    """

    def __init__(self, n, directory=None, poll=0.25):
        if not 1 <= n <= MAX_JOBS:
            raise ValueError("jobs must be between 1 and %d (the archive's limit), not %r" % (MAX_JOBS, n))
        self.n = n
        self.poll = poll
        self.directory = directory if (directory and fcntl) else None
        self._sem = threading.BoundedSemaphore(n)
        self._lock = threading.Lock()
        self.in_flight = 0
        self.peak = 0
        if self.directory:
            os.makedirs(self.directory, exist_ok=True)

    def _take_file(self):
        while True:
            for i in range(self.n):
                fd = os.open(os.path.join(self.directory, "slot%d.lock" % i), os.O_RDWR | os.O_CREAT, 0o644)
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return fd
                except OSError:
                    os.close(fd)
            time.sleep(self.poll)

    @contextlib.contextmanager
    def acquire(self):
        self._sem.acquire()
        fd = None
        try:
            if self.directory:
                fd = self._take_file()
            with self._lock:
                self.in_flight += 1
                self.peak = max(self.peak, self.in_flight)
            try:
                yield
            finally:
                with self._lock:
                    self.in_flight -= 1
        finally:
            if fd is not None:
                os.close(fd)  # closing the file releases the lock
            self._sem.release()


# --------------------------------------------------------------------------
# Files on disk
# --------------------------------------------------------------------------

def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Store:
    """The output folder: one file per source, and events.jsonl, an append-only log."""

    def __init__(self, out):
        self.out = out
        os.makedirs(out, exist_ok=True)
        self.events_path = os.path.join(out, "events.jsonl")
        self._lock = threading.Lock()

    def source_file(self, release, structure, source_id):
        rel = os.path.join(release.replace(" ", "_"), structure, source_id + ".csv")
        return rel, os.path.join(self.out, rel)

    def save_atomic(self, path, data):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".part"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)

    def log(self, event):
        event = dict(event)
        event["t"] = utc_now()
        line = json.dumps(event, sort_keys=True) + "\n"
        with self._lock:
            with open(self.events_path, "a") as f:
                f.write(line)

    def keep_rejected(self, source_ids, data, note):
        """Keep a file that failed its checks, so a person can look at it. Capped at 5 MB each."""
        name = "%s-%s.bin" % (source_ids[0] if source_ids else "none", hashlib.sha256(data).hexdigest()[:10])
        path = os.path.join(self.out, "rejected", name)
        self.save_atomic(path, data[:5_000_000])
        self.log({"event": "rejected_kept", "file": os.path.join("rejected", name), "note": note})

    def state(self, release, structure):
        """{source_id: last 'source' event} for this release and structure."""
        last = {}
        if not os.path.exists(self.events_path):
            return last
        with open(self.events_path) as f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue  # a half-written last line after a crash
                if e.get("event") == "source" and e.get("release") == release and e.get("structure") == structure:
                    last[e["source_id"]] = e
        return last

    def is_done(self, e, retry_no_data):
        if e["status"] == "no_data":
            return not retry_no_data
        if e["status"] != "ok":
            return False
        path = os.path.join(self.out, e["file"])
        return os.path.exists(path) and os.path.getsize(path) == e["bytes"]


# --------------------------------------------------------------------------
# The fetcher
# --------------------------------------------------------------------------

class Config:
    def __init__(self, out, release="Gaia DR3", structure="DATAMODEL_STANDARD", fmt="CSV", batch_size=20,
                 jobs=2, min_interval=1.0, max_attempts=6, split_after=2, backoff_base=2.0, backoff_cap=120.0,
                 max_wait=900.0, timeout=300.0, max_requests=0, abort_after=12, confirm_empty=True,
                 confirm_missing=True, retry_no_data=False, slots_dir=None, base_url=DATA_URL, max_ids=ANON_MAX_IDS):
        self.__dict__.update(locals())
        del self.__dict__["self"]
        self.check()

    def check(self):
        if self.structure in OLD_STRUCTURE_NAMES:
            raise ValueError("%s was renamed. Use %s." % (self.structure, OLD_STRUCTURE_NAMES[self.structure]))
        if self.structure not in STRUCTURES:
            raise ValueError("structure must be one of %s" % ", ".join(STRUCTURES))
        if self.fmt not in FORMATS:
            raise ValueError("format must be one of %s" % ", ".join(FORMATS))
        if self.release not in PROFILES:
            raise ValueError("release must be one of %s" % ", ".join(PROFILES))
        if self.structure == "DATAMODEL_GAIA" and PROFILES[self.release].gaia_columns is None:
            raise ValueError("DATAMODEL_GAIA is not supported for %s yet (its layout is not known)" % self.release)
        if not 1 <= self.jobs <= MAX_JOBS:
            raise ValueError("jobs must be between 1 and %d (the archive's limit), not %r" % (MAX_JOBS, self.jobs))
        if self.jobs > QUEUE_LIMIT:
            raise ValueError("jobs cannot exceed the queue limit of %d" % QUEUE_LIMIT)
        if not 1 <= self.batch_size <= self.max_ids:
            raise ValueError("batch size must be between 1 and %d, not %r" % (self.max_ids, self.batch_size))
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")


class Fetcher:
    def __init__(self, cfg, transport=None, sleep=None, rng=None, log=None):
        self.cfg = cfg
        self.transport = transport or Transport(cfg.timeout)
        self.store = Store(cfg.out)
        self.profile = PROFILES[cfg.release]
        self.rng = rng or random.Random()
        self.log = log or logging.getLogger("gaia_datalink")
        self.stop = threading.Event()
        self._sleep = sleep or (lambda s: self.stop.wait(s))
        self.slots = SlotPool(cfg.jobs, cfg.slots_dir)
        self.max_ids = cfg.batch_size
        self._lock = threading.Lock()
        self._next_start = 0.0
        self._cooldown_until = 0.0
        self.requests = 0
        self.bad_streak = 0          # failed requests and unusable answers in a row (see _answer_bad)
        self.check_reasons = {}      # source ID -> why its file failed the checks, for the 'failed' log line
        self.counts = collections.Counter()
        self.rows = 0
        self.request_seconds = []

    # ---- one request ----

    def build_url(self, ids):
        q = [("RETRIEVAL_TYPE", "EPOCH_PHOTOMETRY"), ("ID", ",".join(ids)), ("RELEASE", self.cfg.release),
             ("FORMAT", self.cfg.fmt), ("DATA_STRUCTURE", self.cfg.structure)]
        return self.cfg.base_url + "?" + urllib.parse.urlencode(q, quote_via=urllib.parse.quote_plus)

    def _wait_turn(self):
        """Keep `min_interval` seconds between request starts, and honour a global cool-down."""
        with self._lock:
            now = time.monotonic()
            start = max(now, self._next_start, self._cooldown_until)
            self._next_start = start + self.cfg.min_interval
        if start > now:
            self._sleep(start - now)

    def _send(self, ids, attempt, second_look=False):
        if self.stop.is_set():
            raise Aborted("stopped")
        self._wait_turn()
        with self.slots.acquire():
            with self._lock:
                if self.cfg.max_requests and self.requests >= self.cfg.max_requests:
                    self.stop.set()
                    raise Aborted("reached --max-requests %d" % self.cfg.max_requests)
                self.requests += 1
                number = self.requests
            url = self.build_url(ids)
            t0 = time.monotonic()
            try:
                resp = self.transport.get(url)
                outcome = classify(resp)
            except TransportError as e:
                resp, outcome = None, Outcome("retry", "network error: %s" % e)
            seconds = time.monotonic() - t0
        self.request_seconds.append(seconds)
        status = resp.status if resp else None
        size = len(resp.body) if resp else 0
        self.store.log({
            "event": "request", "n": number, "ids": ids, "structure": self.cfg.structure, "release": self.cfg.release,
            "attempt": attempt, "second_look": second_look, "http_status": status, "seconds": round(seconds, 2),
            "bytes": size,
            "content_type": resp.headers.get("content-type") if resp else None,
            "outcome": outcome.kind, "message": outcome.message[:300],
        })
        self.log.info("request %d: %d ids, attempt %d -> %s, %.1f s, %d bytes, %s%s", number, len(ids), attempt,
                      status, seconds, size, outcome.kind, (" (%s)" % outcome.message[:100]) if outcome.message else "")
        with self._lock:
            if outcome.kind in ("retry", "queue"):
                self.bad_streak += 1
                if self.bad_streak >= self.cfg.abort_after:
                    self.stop.set()
                    raise Aborted("%d requests in a row failed; the service looks unavailable. "
                                  "Start the same command later to resume." % self.bad_streak)
            elif outcome.kind == "empty":
                self.bad_streak = 0  # an empty answer is a valid answer. A data answer counts only once it is accepted
        return resp, outcome

    def _answer_bad(self, why):
        """An answer came back but could not be used. It counts like a failed request: after `abort_after` in a
        row the run stops, because the archive is down or its files no longer look as expected."""
        with self._lock:
            self.bad_streak += 1
            streak = self.bad_streak
        self.log.warning("unusable answer, %d in a row: %s", streak, why)
        if streak >= self.cfg.abort_after:
            self.stop.set()
            raise Aborted("%d answers in a row were unusable (failed requests, or files that failed their checks). "
                          "If the files are the problem, check rejected/ and the release. Otherwise start the same "
                          "command later to resume." % streak)

    def _answer_good(self):
        with self._lock:
            self.bad_streak = 0

    def _backoff(self, attempt, outcome):
        """Set a cool-down for all workers: exponential, with jitter, at least Retry-After, at most max_wait."""
        delay = min(self.cfg.backoff_cap, self.cfg.backoff_base * 2 ** (attempt - 1))
        delay *= 0.5 + self.rng.random() / 2  # jitter, so parallel workers do not retry together
        if outcome.kind == "queue":
            delay = max(delay, 30.0)
        delay = min(max(delay, outcome.retry_after), self.cfg.max_wait)
        with self._lock:  # every worker holds back, not only this one
            self._cooldown_until = max(self._cooldown_until, time.monotonic() + delay)
        return delay

    # ---- one batch ----

    def fetch_ids(self, ids, second_look=False):
        """Fetch these sources, splitting, retrying and recording until each has a final status.

        `second_look` marks a request that only confirms "no data": the sources were missing from an earlier
        answer, and whatever this request says about them is final.
        """
        if len(ids) > self.max_ids:  # a limit learned from the archive since this batch was planned
            for i in range(0, len(ids), self.max_ids):
                self.fetch_ids(ids[i:i + self.max_ids], second_look)
            return
        pending = list(ids)
        attempt = 0
        confirmed_empty = False
        while pending:
            attempt += 1
            resp, outcome = self._send(pending, attempt, second_look)
            k = outcome.kind
            if k == "fatal":
                self.stop.set()
                raise FatalError(outcome.message)
            if k == "too_many":
                with self._lock:
                    self.max_ids = max(1, min(self.max_ids, outcome.limit))
                    size = self.max_ids
                self.log.warning("the archive allows at most %d ids per request; splitting", outcome.limit)
                for i in range(0, len(pending), size):
                    self.fetch_ids(pending[i:i + size], second_look)
                return
            if k == "empty":
                if self.cfg.confirm_empty and not confirmed_empty and not second_look:
                    confirmed_empty = True  # ask once more before believing "no data"
                    self._sleep(1.0)
                    continue
                self._record_all(pending, "no_data", resp, "the archive returned an empty answer" +
                                 (" twice" if confirmed_empty else " when asked a second time" if second_look else ""))
                return
            if k == "data":
                try:
                    again, absent = self._accept(pending, resp, second_look)
                except ValidationError as e:
                    self.store.keep_rejected(pending, resp.body, str(e))
                    self._answer_bad("the whole answer failed its checks: %s" % e)
                    outcome = Outcome("retry", "invalid answer: %s" % e)
                    k = "retry"
                else:
                    if again:
                        self._answer_bad("%d sources failed their checks" % len(again))
                    else:
                        self._answer_good()
                    if absent:  # missing from a non-empty answer: ask for them once more before calling it "no data"
                        self.fetch_ids(absent, second_look=True)
                    pending = again
                    if not pending:
                        return
                    outcome = Outcome("retry", "some sources failed their checks")
                    k = "retry"
            if k == "fail":
                if len(pending) > 1:
                    self._split(pending, second_look)
                else:
                    self._record_all(pending, "failed", resp, outcome.message)
                return
            # a temporary problem
            if attempt >= self.cfg.max_attempts:
                if len(pending) > 1:
                    self._split(pending, second_look)
                else:
                    self._record_all(pending, "failed", resp, "gave up after %d attempts: %s" % (attempt, outcome.message))
                return
            if attempt >= self.cfg.split_after and len(pending) > 1:
                self._split(pending, second_look)  # find out which source is the trouble, and ease the load
                return
            # The wait itself happens in _wait_turn, which every worker passes before sending.
            delay = self._backoff(attempt, outcome)
            self.log.info("waiting %.1f s before attempt %d", delay, attempt + 1)

    def _split(self, pending, second_look=False):
        mid = len(pending) // 2
        self.log.info("splitting %d ids into %d and %d", len(pending), mid, len(pending) - mid)
        self.fetch_ids(pending[:mid], second_look)
        self.fetch_ids(pending[mid:], second_look)

    # ---- turning an answer into files ----

    def _accept(self, pending, resp, second_look=False):
        """Check and save what came back.

        Returns (again, absent). `again` are sources whose file failed its checks: ask for them again.
        `absent` are sources missing from the answer, still to be confirmed with a second look. When no
        second look is wanted (or this already is one) they are recorded as no_data here and `absent` is empty.
        """
        asked = set(pending)
        again = []
        if self.cfg.structure == "DATAMODEL_STANDARD":
            parts = split_standard(resp.body, self.cfg.structure)
            unexpected = set(parts) - asked
            if unexpected:
                raise ValidationError("the answer holds sources that were not asked for: %s" % sorted(unexpected)[:3])
            for sid in pending:
                if sid not in parts:
                    continue
                try:
                    info = check_standard_csv(parts[sid], sid, self.profile)
                except ValidationError as e:
                    self.store.keep_rejected([sid], parts[sid], str(e))
                    self._failed_check(sid, e)
                    again.append(sid)
                    continue
                self._record_ok(sid, parts[sid], info, resp, len(pending))
        else:
            header, rows = split_gaia(resp.body)
            unexpected = set(rows) - asked
            if unexpected:
                raise ValidationError("the answer holds sources that were not asked for: %s" % sorted(unexpected)[:3])
            for sid in pending:
                if sid not in rows:
                    continue
                buf = io.StringIO()
                w = csv.writer(buf, lineterminator="\n")
                w.writerow(header)
                w.writerow(rows[sid])
                data = buf.getvalue().encode("utf-8")  # this source's row as a one-row CSV, the same as a saved file
                try:
                    info = check_gaia_row(header, rows[sid], sid, self.profile)
                except ValidationError as e:
                    self.store.keep_rejected([sid], data, str(e))
                    self._failed_check(sid, e)
                    again.append(sid)
                    continue
                self._record_ok(sid, data, info, resp, len(pending))
        # Sources missing from a non-empty answer have no epoch photometry.
        got = set(parts) if self.cfg.structure == "DATAMODEL_STANDARD" else set(rows)
        absent = [s for s in pending if s not in got]
        if absent and (second_look or not self.cfg.confirm_missing):
            self._record_all(absent, "no_data", resp, "not in a non-empty answer" +
                             (", and not in the answer to a second request" if second_look else ""),
                             batch_size=len(pending))
            absent = []
        return again, absent

    def _failed_check(self, sid, err):
        self.log.warning("source %s failed its checks: %s", sid, err)
        with self._lock:
            self.check_reasons[sid] = str(err)

    def _record_ok(self, sid, data, info, resp, batch_size):
        rel, path = self.store.source_file(self.cfg.release, self.cfg.structure, sid)
        self.store.save_atomic(path, data)
        self._source_event(sid, "ok", resp, batch_size, file=rel, bytes=len(data),
                           sha256=hashlib.sha256(data).hexdigest(), **info)
        with self._lock:
            self.check_reasons.pop(sid, None)
            self.counts["ok"] += 1
            self.rows += info["rows"]

    def _record_all(self, ids, status, resp, message, batch_size=None):
        for sid in ids:
            msg = message
            if status == "failed" and sid in self.check_reasons:  # say why its file was refused, not only that it was
                msg = "%s (last check: %s)" % (message, self.check_reasons[sid])
            self._source_event(sid, status, resp, batch_size or len(ids), message=msg)
        with self._lock:
            self.counts[status] += len(ids)

    def _source_event(self, sid, status, resp, batch_size, **extra):
        e = {"event": "source", "source_id": sid, "release": self.cfg.release, "structure": self.cfg.structure,
             "format": self.cfg.fmt, "status": status, "http_status": resp.status if resp else None,
             "batch_size": batch_size, "archive_content_type": resp.headers.get("content-type") if resp else None}
        e.update(extra)
        self.store.log(e)

    # ---- the whole run ----

    def run(self, ids):
        """Fetch every source in `ids` that is not already done. Returns a summary dict."""
        self._t0 = time.monotonic()
        state = self.store.state(self.cfg.release, self.cfg.structure)
        todo = [i for i in ids if not (i in state and self.store.is_done(state[i], self.cfg.retry_no_data))]
        skipped = len(ids) - len(todo)
        batches = [todo[i:i + self.max_ids] for i in range(0, len(todo), self.max_ids)]
        self.log.info("%d sources asked, %d already done, %d to fetch in %d batches of up to %d, %d jobs at most",
                      len(ids), skipped, len(todo), len(batches), self.max_ids, self.cfg.jobs)
        if self.cfg.release == "Gaia DR4":
            self.log.warning("the DR4 checks are a guess: %s", self.profile.note)
        self.store.log({"event": "run_start", "version": VERSION, "release": self.cfg.release,
                        "structure": self.cfg.structure, "sources": len(ids), "already_done": skipped,
                        "batches": len(batches), "jobs": self.cfg.jobs, "batch_size": self.max_ids})
        errors = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.cfg.jobs) as pool:
            futures = [pool.submit(self.fetch_ids, b) for b in batches]
            try:
                for f in concurrent.futures.as_completed(futures):
                    try:
                        f.result()
                    except (FatalError, Aborted) as e:
                        errors.append(e)
                        self.stop.set()
            except KeyboardInterrupt:
                self.stop.set()
                errors.append(Aborted("interrupted; start the same command again to resume"))
                for f in futures:
                    f.cancel()
        # Report a fatal error in preference to the 'stopped' errors it caused in other workers.
        error = next((e for e in errors if isinstance(e, FatalError)), errors[0] if errors else None)
        elapsed = time.monotonic() - self._t0
        summary = {
            "sources_asked": len(ids), "already_done_before_run": skipped,
            "ok": self.counts["ok"], "no_data": self.counts["no_data"], "failed": self.counts["failed"],
            "not_attempted": len(todo) - self.counts["ok"] - self.counts["no_data"] - self.counts["failed"],
            "requests": self.requests, "peak_open_requests": self.slots.peak, "jobs_limit": self.cfg.jobs,
            "rows": self.rows, "seconds": round(elapsed, 1),
            "request_seconds_mean": round(sum(self.request_seconds) / len(self.request_seconds), 2)
            if self.request_seconds else None,
            "stopped_because": str(error) if error else None,
        }
        self.store.log(dict(summary, event="run_end"))
        with open(os.path.join(self.cfg.out, "summary.json"), "w") as f:
            json.dump(summary, f, indent=1)
        if error:
            summary["error"] = error
        return summary


# --------------------------------------------------------------------------
# Reading ID files, checking a finished run, the command line
# --------------------------------------------------------------------------

def read_ids(path, release="Gaia DR3"):
    """Gaia source IDs from a text or CSV file. Accepts 123, 'Gaia DR3 123', and a CSV with a source_id column.

    A designation that names another release ('Gaia DR2 123' in a DR3 run) is refused. Otherwise the
    number would be fetched from the wrong release without any warning.
    """
    ids, seen = [], set()
    with open(path, newline="") as f:
        lines = [ln.strip() for ln in f if ln.strip() and not ln.lstrip().startswith("#")]
    column = None
    if lines and not re.match(r"^(Gaia\s+DR\d\s+)?\d+$", lines[0], flags=re.I):
        header = [h.strip() for h in next(csv.reader([lines[0]]))]
        if "source_id" not in header:
            raise ValueError("the first line is not an ID and not a CSV header with a source_id column")
        column = header.index("source_id")
        lines = lines[1:]
    run_dr = release.split()[-1].upper()  # 'DR3' for 'Gaia DR3'
    for ln in lines:
        raw = next(csv.reader([ln]))[column] if column is not None else ln
        m = re.fullmatch(r"(?:Gaia\s+(DR\d)\s+)?(\d{1,19})", raw.strip(), flags=re.I)
        if not m or not 0 < int(m.group(2)) < 2 ** 63:
            raise ValueError("not a Gaia source ID: %r" % raw[:40])
        if m.group(1) and m.group(1).upper() != run_dr:
            raise ValueError("%r is a %s designation, but this run is for %s (--release). "
                             "Use IDs of that release, or a plain number." % (raw[:40], m.group(1).upper(), release))
        sid = str(int(m.group(2)))
        if sid not in seen:
            seen.add(sid)
            ids.append(sid)
    return ids


def check_run(out, release, structure):
    """Re-check every saved file of a finished run: it exists, its checksum matches, it passes the checks."""
    store = Store(out)
    profile = PROFILES[release]
    state = store.state(release, structure)
    problems, ok = [], 0
    for sid, e in sorted(state.items()):
        if e["status"] != "ok":
            continue
        path = os.path.join(out, e["file"])
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError:
            problems.append((sid, "file is missing"))
            continue
        if hashlib.sha256(data).hexdigest() != e["sha256"]:
            problems.append((sid, "checksum differs from the log"))
            continue
        try:
            if structure == "DATAMODEL_STANDARD":
                check_standard_csv(data, sid, profile)
            else:
                rows = read_csv_rows(data.decode("utf-8"))  # a cell the csv module cannot read is a problem, not a crash
                if len(rows) != 2:
                    raise ValidationError("expected a header and one row, found %d lines" % len(rows))
                check_gaia_row(rows[0], rows[1], sid, profile)
            ok += 1
        except (ValidationError, IndexError, UnicodeDecodeError) as ex:
            problems.append((sid, str(ex)))
    counts = collections.Counter(e["status"] for e in state.values())
    return {"sources_in_log": len(state), "status_counts": dict(counts), "files_ok": ok, "problems": problems}


def make_parser():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--release", default="Gaia DR3", choices=sorted(PROFILES))
    common.add_argument("--structure", default="DATAMODEL_STANDARD",
                        help="DATAMODEL_STANDARD (one row per epoch) or DATAMODEL_GAIA (one row per source). "
                             "INDIVIDUAL and RAW are the old names and are refused.")
    f = sub.add_parser("fetch", parents=[common], help="download epoch photometry for a file of source IDs")
    f.add_argument("ids_file", help="one source ID per line (or a CSV with a source_id column)")
    f.add_argument("--out", required=True, help="output folder (files, events.jsonl, summary.json)")
    f.add_argument("--batch-size", type=int, default=20,
                   help="sources per request (default 20; anonymous maximum is %d)" % ANON_MAX_IDS)
    f.add_argument("--jobs", type=int, default=2,
                   help="requests open at once (default 2, never more than %d)" % MAX_JOBS)
    f.add_argument("--min-interval", type=float, default=1.0, help="seconds between request starts (default 1)")
    f.add_argument("--max-attempts", type=int, default=6)
    f.add_argument("--timeout", type=float, default=300.0,
                   help="seconds to wait without receiving any data from the archive (default 300)")
    f.add_argument("--max-requests", type=int, default=0, help="stop after this many requests (0 = no limit)")
    f.add_argument("--retry-no-data", action="store_true", help="ask again for sources logged as having no data")
    f.add_argument("--no-second-look", action="store_true",
                   help="do not send a second request to confirm 'no data' (by default a source missing from an "
                        "answer, or an empty answer, is asked for once more before it is recorded as no_data)")
    f.add_argument("--slots-dir", default=os.environ.get("GAIA_DATALINK_SLOTS_DIR") or os.path.join(
        os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "f0-gaia-datalink", "slots"),
        help="folder of lock files that share the job limit between runs (default: ~/.cache/f0-gaia-datalink/slots)")
    f.add_argument("--login", action="store_true",
                   help="sign in first. Reads GAIA_USER and GAIA_PASSWORD from the environment, or asks. "
                        "UNTESTED against the real archive.")
    f.add_argument("--dry-run", action="store_true", help="show the plan and send nothing")
    c = sub.add_parser("check", parents=[common], help="re-check the files of a finished run")
    c.add_argument("out")
    return ap


def main(argv=None):
    args = make_parser().parse_args(argv)
    if args.cmd == "check":
        res = check_run(args.out, args.release, args.structure)
        print(json.dumps(res, indent=1))
        return 0 if not res["problems"] else 2
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S", stream=sys.stderr)
    try:
        max_ids = SIGNED_IN_MAX_IDS if args.login else ANON_MAX_IDS
        cfg = Config(args.out, release=args.release, structure=args.structure, batch_size=args.batch_size,
                     jobs=args.jobs, min_interval=args.min_interval, max_attempts=args.max_attempts,
                     timeout=args.timeout, max_requests=args.max_requests, retry_no_data=args.retry_no_data,
                     confirm_empty=not args.no_second_look, confirm_missing=not args.no_second_look,
                     slots_dir=args.slots_dir, max_ids=max_ids)
        ids = read_ids(args.ids_file, args.release)
        if not ids:
            raise ValueError("the file holds no source IDs")
    except (ValueError, OSError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 3
    if args.dry_run:
        n = -(-len(ids) // cfg.batch_size)
        print("%d sources, %d requests of up to %d, %d jobs at most; nothing sent" % (len(ids), n, cfg.batch_size, cfg.jobs))
        return 0
    transport = Transport(cfg.timeout)
    if args.login:
        user = os.environ.get("GAIA_USER") or input("Gaia archive user name: ")
        password = os.environ.get("GAIA_PASSWORD") or getpass.getpass("Gaia archive password: ")
        try:
            sign_in(transport, user, password)
        except FatalError as e:
            print("error: %s" % e, file=sys.stderr)
            return 3
        del password
    fetcher = Fetcher(cfg, transport)
    fh = logging.FileHandler(os.path.join(cfg.out, "fetch.log"))
    fh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logging.getLogger("gaia_datalink").addHandler(fh)
    try:
        summary = fetcher.run(ids)
    finally:
        logging.getLogger("gaia_datalink").removeHandler(fh)
        fh.close()
    print(json.dumps({k: v for k, v in summary.items() if k != "error"}, indent=1))
    err = summary.get("error")
    if isinstance(err, FatalError):
        print("error: %s" % err, file=sys.stderr)
        return 3
    if err:
        print("stopped: %s" % err, file=sys.stderr)
        return 4
    if summary["failed"]:
        return 2
    if summary["sources_asked"] > 5 and summary["ok"] == 0 and summary["already_done_before_run"] == 0:
        # Not an error in the log, but a wrong release or wrong IDs look exactly like this, so say so.
        print("warning: none of the %d sources has data in %s (%s). Check the IDs and --release."
              % (summary["sources_asked"], cfg.release, cfg.structure), file=sys.stderr)
        return 5
    return 0


if __name__ == "__main__":
    sys.exit(main())
