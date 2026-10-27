"""Anonymous TAP queries to MAST (TESS Input Catalog), the Gaia archive and SIMBAD.

TAP is the Table Access Protocol, a standard way to send a database query (written in
ADQL, a form of SQL for astronomy) to an archive over the web.

All three services are used without any account. Each query goes through httpcache.fetch,
so a repeated query reads the saved answer and sends nothing.
"""

import csv
import io
import xml.etree.ElementTree as ET

import httpcache

MAST_TIC_TAP = "https://mast.stsci.edu/vo-tap/api/v0.1/tic/sync"
GAIA_TAP = "https://gea.esac.esa.int/tap-server/tap/sync"
SIMBAD_TAP = "https://simbad.cds.unistra.fr/simbad/sim-tap/sync"

BATCH = 100  # identifiers per query


def id_list(ids):
    """Turn integers (or digit strings) into '1,2,3' for an ADQL IN (...) list.

    Every value goes through int(), so nothing but digits can reach the query text,
    whatever the input file contained.
    """
    clean = [int(i) for i in ids]
    if not clean:
        raise ValueError("empty identifier list")
    return ",".join(str(i) for i in clean)


def batches(items, size=BATCH):
    items = list(items)
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def parse_votable(body):
    """Parse a VOTable written as TABLEDATA. Returns (list of column names, list of rows).

    Rows are lists of strings. An empty cell is returned as ''.
    A VOTable can also carry an error message instead of a table (an INFO element named
    QUERY_STATUS with the value ERROR). That raises ValueError.
    """
    root = ET.fromstring(body)
    names, rows = [], []
    for el in root.iter():
        tag = _local(el.tag)
        if (tag == "INFO" and (el.get("name") or "").upper() == "QUERY_STATUS"
                and (el.get("value") or "").upper() == "ERROR"):
            raise ValueError("the service reported an error: %s" % (el.text or "").strip()[:200])
        if tag == "FIELD":
            names.append(el.get("name"))
        elif tag == "TR":
            rows.append([(td.text or "") for td in el if _local(td.tag) == "TD"])
    for r in rows:
        if len(r) != len(names):
            raise ValueError("VOTable row has %d cells, expected %d" % (len(r), len(names)))
    return names, rows


def parse_csv(body):
    reader = csv.reader(io.StringIO(body.decode("utf-8")))
    rows = list(reader)
    if not rows:
        raise ValueError("empty CSV answer")
    return rows[0], rows[1:]


def check_votable(body, require=()):
    """Return a message if `body` is not a VOTable table with the columns in `require`,
    else None. An error document from the service has no such columns, so it fails here
    and is never saved.
    """
    try:
        names, _ = parse_votable(body)
    except (ET.ParseError, ValueError) as exc:
        return "not a readable VOTable table (%s)" % exc
    missing = [c for c in require if c not in names]
    if missing:
        return "the answer lacks column(s) %s, so it is not the table that was asked for" % (
            ", ".join(missing))
    return None


def mast_query(data_dir, kind, adql, offline=False, require=()):
    """Run ADQL on the MAST TIC service. Returns (names, rows, info).

    `require` lists columns that the answer must have. An answer without them (for example
    an error document) raises FetchError and is not saved. A table with the right columns
    and no rows is a valid answer: it means none of the IDs is in the TIC.
    """
    body, info = httpcache.fetch(
        data_dir, kind, MAST_TIC_TAP,
        data={"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "votable", "QUERY": adql},
        offline=offline, reject=lambda b: check_votable(b, require))
    problem = check_votable(body, require)  # also covers an answer saved earlier
    if problem:
        raise httpcache.FetchError("%s for %s" % (problem, MAST_TIC_TAP))
    names, rows = parse_votable(body)
    return names, rows, info


def csv_query(data_dir, kind, url, adql, offline=False):
    """Run ADQL on a TAP service that can answer in CSV (Gaia archive, SIMBAD)."""
    def reject(body):
        head = body.lstrip()[:200].lower()
        if head.startswith(b"<?xml") or head.startswith(b"<votable"):
            # The service answered with an error document, not a table.
            return "service returned XML instead of CSV"
        return None

    body, info = httpcache.fetch(
        data_dir, kind, url,
        data={"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": adql},
        offline=offline, reject=reject)
    names, rows = parse_csv(body)
    return names, rows, info


def gaia_query(data_dir, kind, adql, offline=False):
    return csv_query(data_dir, kind, GAIA_TAP, adql, offline=offline)


def simbad_query(data_dir, kind, adql, offline=False):
    return csv_query(data_dir, kind, SIMBAD_TAP, adql, offline=offline)
