"""Check that every table and column a query file uses exists.

    python3 -I check_columns.py dr3            # dr3/*.adql against results/dr3_tap_schema_columns.csv
    python3 -I check_columns.py dr4            # dr4/*.adql and dr4_only/*.adql against the draft data model (datamodel/dr4_draft_columns.tsv)
    python3 -I check_columns.py dr3 --live     # dr3/*.adql against the live archive's TAP_SCHEMA (one request)
    python3 -I check_columns.py dr4 --live     # RELEASE DAY: dr4/*.adql against the real DR4 TAP_SCHEMA (one request)

The exit status is 0 if nothing is missing and 1 otherwise. On release day run the last form first
(RUNBOOK.md, step 1). It asks the archive for `TAP_SCHEMA.columns` of the tables the queries use.
If DR4 sits at another address, set --tap-url.

The check reads query text only. It cannot tell whether a column still means the same thing.
Compare the notes in column_map.tsv with the published data model for that.
"""
import csv
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ALIAS = re.compile(r"\b(?:FROM|JOIN)\s+([A-Za-z_]\w*\.[A-Za-z_]\w*)\s+AS\s+([A-Za-z_]\w*)", re.I)
QUALIFIED = re.compile(r"\b([A-Za-z_]\w*)\.([A-Za-z_]\w*)\b")


def used_columns(files):
    """Return {schema.table: set(columns)} for the given query files."""
    found = {}
    for path in files:
        with open(path, encoding="utf-8") as f:
            text = "\n".join(line.split("--", 1)[0] for line in f)
        aliases = {a: t for t, a in ALIAS.findall(text)}
        for t in aliases.values():
            found.setdefault(t, set())
        for a, c in QUALIFIED.findall(text):
            if a in aliases:
                found[aliases[a]].add(c)
    return found


def known_dr3():
    out = {}
    with open(os.path.join(HERE, "results", "dr3_tap_schema_columns.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.setdefault(r["table_name"], set()).add(r["column_name"])
    return out


def known_dr4_draft():
    out = {}
    with open(os.path.join(HERE, "datamodel", "dr4_draft_columns.tsv"), encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            out.setdefault("gaiadr4." + r["table"], set()).add(r["column"])
    return out


def known_live(tables, tap_url=None):
    if tap_url:
        common.TAP_SYNC = tap_url
    quoted = ",".join("'%s'" % t for t in sorted(tables))
    header, rows = common.tap_query(
        "SELECT table_name, column_name FROM TAP_SCHEMA.columns WHERE table_name IN (%s)" % quoted,
        note="check_columns live")
    out = {}
    for t, c in rows:
        out.setdefault(t, set()).add(c)
    return out


def compare(used, known):
    problems = []
    for table in sorted(used):
        if table not in known:
            problems.append("table not found: %s" % table)
            continue
        for c in sorted(used[table] - known[table]):
            problems.append("column not found: %s.%s" % (table, c))
    return problems


def main(argv):
    if len(argv) < 2 or argv[1] not in ("dr3", "dr4"):
        sys.exit(__doc__)
    release, live = argv[1], "--live" in argv
    tap_url = argv[argv.index("--tap-url") + 1] if "--tap-url" in argv else None
    files = sorted(glob.glob(os.path.join(HERE, release, "*.adql")))
    if release == "dr4":
        files += sorted(glob.glob(os.path.join(HERE, "dr4_only", "*.adql")))
    used = used_columns(files)
    if live:
        known = known_live(used.keys(), tap_url)
        source = "the live archive's TAP_SCHEMA"
    elif release == "dr3":
        known, source = known_dr3(), "results/dr3_tap_schema_columns.csv"
    else:
        known, source = known_dr4_draft(), "the draft DR4 data model"
    problems = compare(used, known)
    n_cols = sum(len(v) for v in used.values())
    print("%d files, %d tables, %d columns, checked against %s" % (len(files), len(used), n_cols, source))
    for p in problems:
        print("  PROBLEM:", p)
    print("OK" if not problems else "%d problem(s)" % len(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
