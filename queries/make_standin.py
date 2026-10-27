"""Turn a DR4 query into its DR3 stand-in, using column_map.tsv. Nothing else changes.

Usage:
    python3 -I make_standin.py dr4/eb_long_period.adql > body.adql

What it does, and all it does:
  1. drops comment text (`--` to the end of the line) and every line tagged `-- DR4ONLY`
     (an output column that has no DR3 equivalent),
  2. renames each table (gaiadr4.x -> gaiadr3.y) using the `table` lines of the map,
  3. renames each alias-qualified column (`eb.frequency`) using the `column` lines.

Rules the query files follow so that this is safe:
  * every table has an alias (`FROM gaiadr4.gaia_source AS gs`),
  * every column is written with its alias (`gs.ra`), never bare,
  * the last item of a SELECT list is never a DR4ONLY line.

The script stops with an error if a column is missing from the map, if an untagged line uses a
column that has no DR3 equivalent, or if a tagged line uses one that has.

On release day the same map, read the other way, tells which names to compare with the real DR4
tables (check_columns.py).
"""
import csv
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MAP = os.path.join(HERE, "column_map.tsv")
TAG = "DR4ONLY"

ALIAS = re.compile(r"\b(?:FROM|JOIN)\s+((?:[A-Za-z_]\w*\.)?[A-Za-z_]\w*)\s+AS\s+([A-Za-z_]\w*)", re.I)
QUALIFIED = re.compile(r"\b([A-Za-z_]\w*)\.([A-Za-z_]\w*)\b")


def load_map(path=MAP):
    tables, cols = {}, {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            if r["kind"] == "table":
                tables[r["dr4_table"]] = r["dr3_table"]
            elif r["dr4_name"] != "-":
                cols[(r["dr4_table"], r["dr4_name"])] = None if r["dr3_name"] == "-" else r["dr3_name"]
    return tables, cols


def aliases_of(text, tables):
    out = {}
    for m in ALIAS.finditer(text):
        qualified, alias = m.group(1), m.group(2)
        if qualified in tables:
            out[alias] = qualified
    return out


def columns_used(line, aliases):
    return [(aliases[a], c) for a, c in QUALIFIED.findall(line) if a in aliases]


def convert(text, map_path=MAP):
    tables, cols = load_map(map_path)
    aliases = aliases_of(text, tables)
    if not aliases:
        raise ValueError("no table with an alias found")
    kept = []
    for line in text.split("\n"):
        tagged = ("--" in line) and (line.split("--", 1)[1].strip().startswith(TAG))
        code = line.split("--", 1)[0].rstrip()
        used = [(t.split(".", 1)[1], c) for t, c in columns_used(code, aliases)]
        for key in used:
            if key not in cols:
                raise ValueError("column %s.%s is not in column_map.tsv" % key)
            if tagged and cols[key] is not None:
                raise ValueError("%s.%s is tagged %s but has a DR3 equivalent (%s)" % (key + (TAG, cols[key])))
            if not tagged and cols[key] is None:
                raise ValueError("%s.%s has no DR3 equivalent but its line is not tagged %s" % (key + (TAG,)))
        if tagged:
            continue
        if code.strip():
            kept.append(code)
    body = "\n".join(kept)

    def sub(m):
        first, second = m.group(1), m.group(2)
        if first in aliases:
            t4 = aliases[first].split(".", 1)[1]
            new = cols[(t4, second)]
            return "%s.%s" % (first, new)
        qualified = "%s.%s" % (first, second)
        if qualified in tables:
            return tables[qualified]
        return m.group(0)

    body = QUALIFIED.sub(sub, body)
    if re.search(r",\s*(FROM|WHERE)\b", body, re.I):
        raise ValueError("a dropped DR4ONLY line left a trailing comma: do not end a SELECT list with one")
    return body.strip() + "\n"


def main(argv):
    if len(argv) != 2:
        sys.exit(__doc__)
    with open(argv[1], encoding="utf-8") as f:
        sys.stdout.write(convert(f.read()))


if __name__ == "__main__":
    main(sys.argv)
