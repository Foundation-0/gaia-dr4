"""Read the text of the draft DR4 data model and list the columns of some tables.

The data model is a PDF (anonftp.cosmos.esa.int, file dated 2026-06-26). Turn it
into text first:

    pdftotext -layout gaia-dr4-prerelease-draft-data-model.pdf model.txt

Then run:

    python3 -I datamodel_columns.py data/datamodel/model.txt datamodel/dr4_draft_columns.tsv

The output is a tab-separated file with one line per column: table, column,
type, unit, short description. It is meant for checks, not as a copy of the
data model. The PDF carries a diagonal "Draft" watermark, whose letters leak
into the text. The cleaning below drops those lines.

Known limit: a few headings are split over lines in an odd order by the PDF
layout. For those, the type or unit may be empty. `check_columns` in
test_datamodel.py lists them.
"""
import os
import re
import sys

TABLES = ["vari_eclipsing_binary", "vari_planetary_transit", "gaia_source",
          "all_source_astrometry", "all_source_photometry", "all_source_match", "all_source_flags",
          "dr3_neighbourhood", "vari_summary"]
WATERMARK = {"D", "ra", "f", "t", "Dr", "aft", "a", "r", "ft", "raf", "Dra", "Draf", "Draft"}
HEADING = re.compile(r"^([a-z][a-z_0-9]*) : (.*)$")
# The PDF layout moved the "(float)" of this heading onto another line. The type was read by eye.
OVERRIDES = {("vari_eclipsing_binary", "delta_global_ranking_bp_min_g"): ("float", "")}


def clean_lines(text):
    out = []
    for line in text.split("\n"):
        s = line.strip().replace("\x0c", "")
        if not s or s in WATERMARK:
            continue
        if s.startswith("Gaia DPAC Document") or s.startswith("CUx"):
            continue
        out.append(line.rstrip())
    return out


def section(lines, name):
    """Lines of the section 'N.M <name> [TAP]' (the second hit; the first is the table of contents)."""
    pat = re.compile(r"^\d+\.\d+\s+%s \[(TAP|DataLink)\]" % re.escape(name))
    starts = [i for i, l in enumerate(lines) if pat.match(l.strip())]
    if not starts:
        raise ValueError("section not found: " + name)
    start = starts[-1]
    nxt = re.compile(r"^\d+\.\d+\s+[a-z_0-9]+ \[(TAP|DataLink)\]")
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if nxt.match(lines[j].strip()):
            end = j
            break
    return lines[start:end]


TYPES = r"(double|float|long|byte|short|int|string|String|boolean|char)"


def split_type_unit(group):
    """'(double, Frequency[day-1 ])' -> ('double', 'day-1')"""
    g = group.strip()[1:-1]
    parts = g.split(",", 1)
    dtype = parts[0].strip()
    unit = ""
    if len(parts) > 1:
        m = re.search(r"\[(.*)\]", parts[1].replace("\n", " "))
        unit = (m.group(1) if m else parts[1]).strip()
    return dtype, unit


def find_group(head):
    """Find the final '(type, unit)' group of a heading; returns (title, group) or (head, None)."""
    for k, ch in enumerate(head):
        if ch != "(":
            continue
        g = head[k:].strip()
        if g.endswith(")") and g.count("(") == g.count(")") and re.match(r"\(" + TYPES + r"\b", g):
            return head[:k].strip(), g
    return head, None


def join_wrapped(a, b):
    """Join two wrapped lines; undo a hyphen break such as 'ge-' + 'ometric'."""
    if a.endswith("-") and b[:1].islower():
        return a[:-1] + b
    return a + " " + b


def parse_columns(sec_lines):
    cols = []
    i = 0
    while i < len(sec_lines):
        m = HEADING.match(sec_lines[i].strip())
        if not m:
            i += 1
            continue
        name, head = m.group(1), m.group(2)
        j = i
        title, group = find_group(head)
        # a heading can wrap over up to three more lines
        while group is None and j + 1 < len(sec_lines) and j - i < 3 \
                and not HEADING.match(sec_lines[j + 1].strip()):
            j += 1
            head = join_wrapped(head, sec_lines[j].strip())
            title, group = find_group(head)
        if group is None:
            j = i  # not found: keep only the first line as the title
            title = m.group(2)
        dtype, unit = split_type_unit(group) if group else ("", "")
        desc = []
        j += 1
        while j < len(sec_lines) and not HEADING.match(sec_lines[j].strip()):
            desc.append(sec_lines[j].strip())
            j += 1
        cols.append({"column": name, "type": dtype, "unit": unit, "title": title,
                     "description": " ".join(desc)})
        i = j
    return cols


def main(model_txt, out_tsv):
    with open(model_txt, encoding="utf-8", errors="replace") as f:
        lines = clean_lines(f.read())
    os.makedirs(os.path.dirname(os.path.abspath(out_tsv)), exist_ok=True)
    n = 0
    with open(out_tsv, "w", encoding="utf-8") as o:
        o.write("table\tcolumn\ttype\tunit\ttitle\n")
        for t in TABLES:
            for c in parse_columns(section(lines, t)):
                if (t, c["column"]) in OVERRIDES:
                    c["type"], c["unit"] = OVERRIDES[(t, c["column"])]
                unit = c["unit"].replace("\u2212", "-")  # the PDF uses a typographic minus
                o.write("\t".join([t, c["column"], c["type"], unit, c["title"]]) + "\n")
                n += 1
    print("wrote %d columns to %s" % (n, out_tsv))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
