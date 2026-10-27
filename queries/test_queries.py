"""Tests on the committed query files and the logs. No network, no downloaded data.

They check that
  * the committed dr4/, dr3/ and dr4_only/ files equal what build_queries.py writes,
  * a DR3 stand-in and its DR4 query differ only in names (same words, numbers and structure),
  * every table and column named exists: DR4 names in the draft data model, DR3 names in the archive's schema,
  * every query ran on DR3 without error, and the counts are the ones logged on 27 Oct 2026.
"""
import csv
import glob
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_queries as bq  # noqa: E402
import check_columns as cc  # noqa: E402
import make_standin as ms  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
QUALIFIED = re.compile(r"\b([A-Za-z_]\w*)\.([A-Za-z_]\w*)\b")


def code_lines(text, drop_dr4only):
    out = []
    for line in text.split("\n"):
        tagged = "--" in line and line.split("--", 1)[1].strip().startswith(ms.TAG)
        if tagged and drop_dr4only:
            continue
        code = line.split("--", 1)[0].strip()
        if code:
            out.append(code)
    return "\n".join(out)


def skeleton(text):
    """The query with every table and column name masked, so that only the structure is left."""
    return QUALIFIED.sub("NAME", text)


def read_log():
    with open(os.path.join(HERE, "results", "run_log.tsv"), encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


class CommittedFilesTests(unittest.TestCase):
    def test_files_equal_the_build(self):
        built = bq.build(write=False)
        self.assertGreater(len(built), 30)
        for rel, text in built.items():
            with open(os.path.join(HERE, rel), encoding="utf-8") as f:
                self.assertEqual(f.read(), text, "%s is out of date: run build_queries.py" % rel)

    def test_no_extra_files(self):
        built = set(os.path.normpath(p) for p in bq.build(write=False))
        on_disk = set(os.path.relpath(p, HERE) for d in ("dr4", "dr3", "dr4_only")
                      for p in glob.glob(os.path.join(HERE, d, "*.adql")))
        self.assertEqual(built, on_disk)

    def test_every_dr4_query_has_a_stand_in(self):
        for p in glob.glob(os.path.join(HERE, "dr4", "*.adql")):
            self.assertTrue(os.path.exists(os.path.join(HERE, "dr3", os.path.basename(p))), p)


class StructureTests(unittest.TestCase):
    def pairs(self):
        for p in sorted(glob.glob(os.path.join(HERE, "dr4", "*.adql"))):
            with open(p, encoding="utf-8") as f:
                t4 = f.read()
            with open(os.path.join(HERE, "dr3", os.path.basename(p)), encoding="utf-8") as f:
                t3 = f.read()
            yield os.path.basename(p), t4, t3

    def test_stand_in_is_the_dr4_query_with_names_changed(self):
        n = 0
        for name, t4, t3 in self.pairs():
            body4 = code_lines(t4, drop_dr4only=True)
            body3 = code_lines(t3, drop_dr4only=False)
            self.assertEqual(skeleton(body4), skeleton(body3), name)
            self.assertEqual(" ".join(ms.convert(t4).split()), " ".join(body3.split()), name)
            n += 1
        self.assertEqual(n, 17)

    def test_only_names_differ(self):
        """Take the DR3 text, put the DR4 names back through the map: the DR4 text must come out (less DR4ONLY lines)."""
        tables, cols = ms.load_map()
        back_t = {v: k for k, v in tables.items()}
        for name, t4, t3 in self.pairs():
            aliases = {}
            for m in ms.ALIAS.finditer(t3):
                aliases[m.group(2)] = m.group(1)
            inv_cols = {}
            for (t, c), c3 in cols.items():
                if c3 is not None:
                    inv_cols[(tables["gaiadr4." + t].split(".")[1], c3)] = c

            def sub(m):
                a, c = m.group(1), m.group(2)
                if a in aliases:
                    return "%s.%s" % (a, inv_cols[(aliases[a].split(".")[1], c)])
                q = "%s.%s" % (a, c)
                return back_t.get(q, q)

            restored = QUALIFIED.sub(sub, code_lines(t3, drop_dr4only=False))
            self.assertEqual(restored, code_lines(t4, drop_dr4only=True), name)

    def test_headers_say_what_they_must(self):
        for name, t4, t3 in self.pairs():
            for key in ("-- Serves:", "-- DR3 stand-in:", "-- Last ran without error on the DR3 stand-in:",
                        "-- DR4 columns this query relies on:", "-- Cannot be tested before release:"):
                self.assertIn(key, t4, name)
            for key in ("-- Serves:", "-- Last ran without error:", "-- DR3 tables used:"):
                self.assertIn(key, t3, name)
            self.assertNotIn("not yet run", t4)
            self.assertNotIn("not yet run", t3)

    def test_every_column_is_written_with_its_alias(self):
        for p in glob.glob(os.path.join(HERE, "dr4", "*.adql")):
            with open(p, encoding="utf-8") as f:
                body = code_lines(f.read(), drop_dr4only=False)
            self.assertNotRegex(body, r"\bSELECT\s+\*", p)
            self.assertNotRegex(body, r"\*\s*FROM", p)

    def test_dr4only_lines_are_never_last_in_the_select_list(self):
        for p in glob.glob(os.path.join(HERE, "dr4", "*.adql")):
            with open(p, encoding="utf-8") as f:
                body = code_lines(f.read(), drop_dr4only=True)
            self.assertNotRegex(body, r",\s*FROM\b", p)


class NamesExistTests(unittest.TestCase):
    def test_dr4_names_are_in_the_draft_data_model(self):
        files = glob.glob(os.path.join(HERE, "dr4", "*.adql")) + glob.glob(os.path.join(HERE, "dr4_only", "*.adql"))
        self.assertEqual(cc.compare(cc.used_columns(files), cc.known_dr4_draft()), [])

    def test_dr3_names_are_in_the_archive_schema(self):
        files = glob.glob(os.path.join(HERE, "dr3", "*.adql"))
        self.assertEqual(cc.compare(cc.used_columns(files), cc.known_dr3()), [])

    def test_the_check_catches_a_wrong_name(self):
        bad = {"gaiadr3.vari_eclipsing_binary": {"period"}, "gaiadr3.nothing": {"x"}}
        self.assertEqual(len(cc.compare(bad, cc.known_dr3())), 2)

    def test_every_table_has_an_alias_and_every_qualifier_resolves(self):
        files = (glob.glob(os.path.join(HERE, "dr4", "*.adql")) + glob.glob(os.path.join(HERE, "dr4_only", "*.adql"))
                 + glob.glob(os.path.join(HERE, "dr3", "*.adql")))
        problems = []
        for path in files:
            with open(path, encoding="utf-8") as f:
                problems += cc.name_problems(f.read())
        self.assertEqual(problems, [])


class ArchiveTablesTests(unittest.TestCase):
    def test_no_tess_table_in_the_archive_on_27_oct_2026(self):
        with open(os.path.join(HERE, "results", "archive_tables.csv"), encoding="utf-8") as f:
            names = [r["table_name"].lower() for r in csv.DictReader(f)]
        self.assertGreater(len(names), 200)
        self.assertEqual([n for n in names if "tess" in n], [])
        self.assertIn("gaiadr3.vari_eclipsing_binary", names)
        self.assertIn("gaiadr3.dr2_neighbourhood", names)


class RunLogTests(unittest.TestCase):
    def last(self, name, variant="full"):
        hit = [r for r in read_log() if r["query"] == name and r["variant"] == variant and r["status"] == "ok"]
        self.assertTrue(hit, "%s never ran without error" % name)
        return hit[-1]

    def test_every_stand_in_ran_without_error(self):
        for p in glob.glob(os.path.join(HERE, "dr3", "*.adql")):
            self.last(os.path.basename(p)[:-5])

    def test_logged_counts(self):
        self.assertEqual(self.last("eb_count_all")["value"], "2184477")
        self.assertEqual(self.last("eb_count_long_period")["value"], "2588")
        self.assertEqual(self.last("pt_count_all")["value"], "214")
        self.assertEqual(self.last("eb_missing_from_gaia_source")["value"], "0")

    def test_the_cut_count_equals_the_rows_of_the_cut_query(self):
        self.assertEqual(self.last("eb_count_long_period_bcut")["value"], self.last("eb_long_period_bcut")["n_rows"])

    def test_rows_equal_counts(self):
        self.assertEqual(self.last("eb_long_period")["n_rows"], self.last("eb_count_long_period")["value"])
        self.assertEqual(self.last("pt_candidates")["n_rows"], self.last("pt_count_all")["value"])

    def test_summary_totals(self):
        with open(os.path.join(HERE, "results", "out", "eb_summary_period.csv"), encoding="utf-8") as f:
            total = sum(int(r["n_sources"]) for r in csv.DictReader(f))
        self.assertEqual(total, int(self.last("eb_count_all")["value"]))

    def test_second_run_gave_the_same_answers(self):
        verifies = [r for r in read_log() if r["variant"].startswith("verify")]
        self.assertGreater(len(verifies), 20, "run run_dr3_checks.py --verify")
        for r in verifies:
            self.assertEqual(r["status"], "ok", r["query"])


if __name__ == "__main__":
    unittest.main()
