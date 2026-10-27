import filecmp
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import ticmap  # noqa: E402


def tic_record(**kw):
    rec = {c: "" for c in ticmap.TIC_COLUMNS}
    rec.update({"id": "1", "version": "20190415", "gaia": "1000", "ra": "10.0", "dec": "20.0",
                "pmra": "100.0", "pmdec": "-50.0", "tmag": "11.0", "gaiamag": "12.0",
                "typesrc": "tmgaia2", "objtype": "STAR", "ra_orig": "10.0", "dec_orig": "20.0",
                "gaiaqflag": "1", "pmflag": "gaia2"})
    rec.update(kw)
    rec["tic"] = rec["id"]
    return rec


def dr3_source(ra=10.0, dec=20.0, **kw):
    s = {"ref_epoch": 2016.0, "ra": ra, "dec": dec, "pmra": 100.0, "pmdec": -50.0,
         "parallax": 5.0, "phot_g_mean_mag": 12.0, "ruwe": 1.0,
         "astrometric_params_solved": 31.0, "duplicated_source": False}
    s.update(kw)
    return s


def nb(dr3, dist=0.2, dmag=0.0, pmprop=True):
    return {"dr3": dr3, "dist": dist, "dmag": dmag, "pmprop": pmprop}


def tic_position_of(src, pmra=100.0, pmdec=-50.0):
    """The TIC position (epoch 2000) of a source whose DR3 position is `src`."""
    from astrometry import propagate
    return propagate(src["ra"], src["dec"], pmra, pmdec, 2000.0 - 2016.0)


class MapOneTests(unittest.TestCase):
    def setUp(self):
        self.src = dr3_source()
        ra, dec = tic_position_of(self.src)
        self.rec = tic_record(ra=repr(ra), dec=repr(dec))
        self.src_map = {2000: self.src}

    def row(self, fwd, rev=None, src=None, rec=None):
        return ticmap.map_one(1, rec or self.rec, {1000: fwd}, rev or {}, src or self.src_map)

    def test_one_to_one(self):
        r = self.row([nb(2000)], {2000: {1000}})
        self.assertEqual(r["status"], "one-to-one")
        self.assertEqual(r["dr3_source_id"], 2000)
        self.assertEqual(r["pos_check"], "ok")
        self.assertEqual(r["needs_judgement"], "no")
        self.assertEqual(r["flags"], "")

    def test_two_neighbours_is_ambiguous_but_clear(self):
        src = {2000: self.src, 2001: dr3_source(ra=10.0004)}
        r = self.row([nb(2000, 0.2), nb(2001, 1500.0, 3.0)], {2000: {1000}, 2001: {1000}}, src)
        self.assertEqual(r["status"], "ambiguous")
        self.assertEqual(r["dr3_source_id"], 2000)
        self.assertEqual(r["runner_up_dr3_source_id"], 2001)
        self.assertEqual(r["n_neighbours"], 2)
        self.assertEqual(r["needs_judgement"], "no")
        self.assertIn("several_dr3_neighbours", r["flags"])

    def test_dr3_shared_with_another_dr2_source_is_ambiguous(self):
        r = self.row([nb(2000)], {2000: {1000, 5555}})
        self.assertEqual(r["status"], "ambiguous")
        self.assertEqual(r["n_dr2_for_dr3"], 2)
        self.assertIn("dr3_shared_with_other_dr2", r["flags"])

    def test_closest_fails_the_magnitude_cut(self):
        src = {2000: self.src, 2001: dr3_source(ra=10.0004)}
        r = self.row([nb(2000, 0.2, 2.5), nb(2001, 900.0, 0.01)], {2000: {1000}, 2001: {1000}}, src)
        self.assertEqual(r["dr3_source_id"], 2001)  # closest of the magnitude-consistent
        self.assertEqual(r["needs_judgement"], "yes")
        self.assertIn("closest_neighbour_fails_magnitude_cut", r["flags"])

    def test_position_prefers_another_neighbour(self):
        far = dr3_source(ra=10.01)  # 35 arcsec away from the TIC position
        src = {2000: far, 2001: self.src}
        r = self.row([nb(2000, 0.2), nb(2001, 900.0)], {2000: {1000}, 2001: {1000}}, src)
        self.assertEqual(r["dr3_source_id"], 2000)
        self.assertEqual(r["nearest_by_position_dr3"], 2001)
        self.assertEqual(r["needs_judgement"], "yes")
        self.assertEqual(r["pos_check"], "large")

    def test_large_position_difference(self):
        rec = tic_record(ra="10.01", dec="20.0")
        r = self.row([nb(2000)], {2000: {1000}}, rec=rec)
        self.assertEqual(r["pos_check"], "large")
        self.assertEqual(r["needs_judgement"], "yes")

    def test_middle_position_difference_is_only_flagged(self):
        ra, dec = tic_position_of(self.src)
        rec = tic_record(ra=repr(ra + 0.5 / 3600 / 0.9397), dec=repr(dec))  # about 0.5 arcsec
        r = self.row([nb(2000)], {2000: {1000}}, rec=rec)
        self.assertEqual(r["pos_check"], "check")
        self.assertEqual(r["needs_judgement"], "no")
        self.assertIn("position_check_0.2_to_1_arcsec", r["flags"])

    def test_no_match(self):
        r = ticmap.map_one(1, self.rec, {}, {}, {})
        self.assertEqual(r["status"], "no match")
        self.assertEqual(r["needs_judgement"], "yes")

    def test_no_dr2_id(self):
        r = ticmap.map_one(1, tic_record(gaia=""), {}, {}, {})
        self.assertEqual(r["status"], "no DR2 ID")
        self.assertEqual(r["needs_judgement"], "yes")

    def test_not_in_tic(self):
        r = ticmap.map_one(7, None, {}, {}, {})
        self.assertEqual(r["status"], "not in TIC")
        self.assertEqual(r["tic"], 7)

    def test_tic_disposition_is_flagged_for_a_person(self):
        rec = tic_record(ra=self.rec["ra"], dec=self.rec["dec"], disposition="DUPLICATE",
                         duplicate_id="42")
        r = self.row([nb(2000)], {2000: {1000}}, rec=rec)
        self.assertEqual(r["needs_judgement"], "yes")
        self.assertIn("tic_disposition_duplicate", r["flags"])
        self.assertIn("tic_duplicate_of_42", r["flags"])

    def test_source_without_proper_motion(self):
        src = dr3_source(pmra=None, pmdec=None, astrometric_params_solved=3.0)
        ra, dec = tic_position_of(src)
        rec = tic_record(ra=repr(ra), dec=repr(dec))
        r = self.row([nb(2000, pmprop=False)], {2000: {1000}}, {2000: src}, rec)
        self.assertIn("proper_motion_from_tic", r["flags"])
        self.assertIn("dr3_two_parameter_solution", r["flags"])
        self.assertIn("no_proper_motion_correction_in_crossmatch", r["flags"])
        self.assertEqual(r["needs_judgement"], "yes")

    def test_duplicated_source_flag(self):
        src = {2000: dr3_source(duplicated_source=True)}
        r = self.row([nb(2000)], {2000: {1000}}, src)
        self.assertIn("dr3_duplicated_source", r["flags"])

    def test_tic_quality_flag_that_is_not_1_is_flagged_for_a_person(self):
        for value in ("0", "-1", ""):
            rec = tic_record(ra=self.rec["ra"], dec=self.rec["dec"], gaiaqflag=value)
            r = self.row([nb(2000)], {2000: {1000}}, rec=rec)
            self.assertIn("tic_gaia_quality_not_passed", r["flags"], value)
            self.assertEqual(r["needs_judgement"], "yes")
            self.assertEqual(r["tic_gaiaqflag"], value)

    def test_tic_proper_motion_not_from_gaia_dr2_is_flagged_for_a_person(self):
        rec = tic_record(ra=self.rec["ra"], dec=self.rec["dec"], pmflag="tgas")
        r = self.row([nb(2000)], {2000: {1000}}, rec=rec)
        self.assertIn("tic_proper_motion_not_from_gaia_dr2", r["flags"])
        self.assertEqual(r["needs_judgement"], "yes")
        self.assertIn("tgas", r["judgement_reasons"])
        self.assertEqual(r["tic_pmflag"], "tgas")

    def test_normal_tic_flags_raise_nothing(self):
        r = self.row([nb(2000)], {2000: {1000}})
        self.assertEqual((r["tic_gaiaqflag"], r["tic_pmflag"]), ("1", "gaia2"))
        self.assertNotIn("tic_", r["flags"])

    def test_proper_motion_propagation_none_counts_as_no_correction(self):
        r = self.row([nb(2000, pmprop=None)], {2000: {1000}})
        self.assertIn("no_proper_motion_correction_in_crossmatch", r["flags"])
        self.assertEqual(r["proper_motion_propagation"], "")

    def test_output_row_has_every_column(self):
        r = self.row([nb(2000)], {2000: {1000}})
        self.assertEqual(list(r), ticmap.OUT_COLUMNS)


class TargetFileTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def write(self, name, text):
        path = os.path.join(self.dir, name)
        with open(path, "w") as fh:
            fh.write(text)
        return path

    def test_plain_list_with_comments_and_prefix(self):
        p = self.write("a.txt", "# my list\n30\nTIC 10\n20\n10\n")
        self.assertEqual(ticmap.read_targets(p), [10, 20, 30])

    def test_csv_with_header(self):
        p = self.write("b.csv", "name,TIC,x\na,5,1\nb,3,2\nc,5,3\n")
        self.assertEqual(ticmap.read_targets(p), [3, 5])

    def test_csv_without_tic_column_is_refused(self):
        p = self.write("c.csv", "name,x\na,1\n")
        with self.assertRaises(ValueError):
            ticmap.read_targets(p)

    def test_non_numeric_id_is_refused(self):
        p = self.write("d.txt", "1\n2; DROP\n")
        with self.assertRaises(ValueError):
            ticmap.read_targets(p)

    def test_eumemic_json(self):
        doc = {"tic": [7, 3, 7], "tiers": ["A", "B"], "tier": [0, 1, 1], "set": [0, 0, 1],
               "ra": [1, 2, 3], "dec": [4, 5, 6], "tmag": [10, 11, 12], "P": [1, 2, 3],
               "rp": [1, 1, 1], "depth": [100, 200, 300]}
        p = self.write("e.json", json.dumps(doc))
        self.assertEqual(ticmap.read_targets(p), [3, 7])
        out = os.path.join(self.dir, "t.csv")
        self.assertEqual(ticmap.eumemic_to_csv(p, out), 3)
        self.assertEqual(ticmap.read_targets(out), [3, 7])


class BooleanTests(unittest.TestCase):
    def test_parse_bool(self):
        self.assertEqual([ticmap.parse_bool(x) for x in ("true", "False", "t", "f", "1", "0", "", "x")],
                         [True, False, True, False, True, False, None, None])

    def test_bool_cell_refuses_text_it_does_not_know(self):
        self.assertIs(ticmap.bool_cell("1", "x"), True)
        self.assertIsNone(ticmap.bool_cell("", "x"))
        with self.assertRaises(ValueError):
            ticmap.bool_cell("maybe", "x")


def small_data():
    """The in-memory form of a tiny download: two targets, one of them not in the TIC."""
    tic = {1: tic_record(id="1", gaia="1000")}
    fwd = [["1000", "2000", "0.2", "0.0", "true"]]
    rev = [["1000", "2000", "0.2", "0.0", "true"]]
    src = [["2000", "2016.0", "10.0", "20.0", "100.0", "-50.0", "5.0", "12.0", "1.0", "31", "false"]]
    info = {"n_targets": 2, "tic": {"found": 1}}
    return [1, 2], tic, fwd, rev, src, info


class SnapshotTests(unittest.TestCase):
    """Snapshots are written all or nothing, and a damaged folder is refused."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        self.snap = os.path.join(self.root, "snap")

    def write(self, **changes):
        ids, tic, fwd, rev, src, info = small_data()
        parts = {"ids": ids, "tic": tic, "fwd": fwd, "rev": rev, "src": src}
        parts.update(changes)
        return ticmap.write_snapshots(self.snap, parts["ids"], parts["tic"], parts["fwd"],
                                      parts["rev"], parts["src"], info)

    def test_round_trip_and_no_leftover_folder(self):
        self.write()
        ids, tic, fwd, rev, src, info = ticmap.load_snapshots(self.snap)
        self.assertEqual(ids, [1, 2])
        self.assertEqual(sorted(tic), [1])
        self.assertIs(fwd[1000][0]["pmprop"], True)
        self.assertIs(src[2000]["duplicated_source"], False)
        self.assertEqual(sorted(info["files"]), sorted(ticmap.SNAPSHOT_FILES))
        self.assertEqual([n for n in os.listdir(self.root) if n.startswith(".")], [])
        rows = ticmap.build_table(ids, tic, fwd, rev, src)
        self.assertEqual([r["status"] for r in rows], ["one-to-one", "not in TIC"])

    def test_one_and_zero_are_read_as_true_and_false(self):
        ids, tic, fwd, rev, src, info = small_data()
        fwd[0][4] = "1"
        src[0][10] = "0"
        ticmap.write_snapshots(self.snap, ids, tic, fwd, rev, src, info)
        _, _, fwd2, _, src2, _ = ticmap.load_snapshots(self.snap)
        self.assertIs(fwd2[1000][0]["pmprop"], True)
        self.assertIs(src2[2000]["duplicated_source"], False)

    def test_unknown_boolean_text_is_refused(self):
        ids, tic, fwd, rev, src, info = small_data()
        fwd[0][4] = "maybe"
        ticmap.write_snapshots(self.snap, ids, tic, fwd, rev, src, info)
        with self.assertRaises(ValueError):
            ticmap.load_snapshots(self.snap)

    def test_a_file_that_does_not_match_run_info_is_refused(self):
        self.write()
        with open(os.path.join(self.snap, "dr2_neighbourhood.csv"), "a") as fh:
            fh.write("1000,2001,5.0,0.0,true\n")
        with self.assertRaises(ValueError) as ctx:
            ticmap.load_snapshots(self.snap)
        self.assertIn("dr2_neighbourhood.csv", str(ctx.exception))

    def test_run_info_without_checksums_is_refused(self):
        self.write()
        path = os.path.join(self.snap, "run_info.json")
        with open(path) as fh:
            info = json.load(fh)
        del info["files"]
        with open(path, "w") as fh:
            json.dump(info, fh)
        with self.assertRaises(ValueError):
            ticmap.load_snapshots(self.snap)

    def test_a_failed_download_leaves_the_old_snapshots_alone(self):
        self.write()
        before = {n: file_bytes(os.path.join(self.snap, n))
                  for n in ticmap.SNAPSHOT_FILES + ["run_info.json"]}
        saved = (ticmap.fetch_tic, ticmap.fetch_dr2n, ticmap.fetch_rev, ticmap.fetch_src)
        self.addCleanup(lambda: (setattr(ticmap, "fetch_tic", saved[0]),
                                 setattr(ticmap, "fetch_dr2n", saved[1]),
                                 setattr(ticmap, "fetch_rev", saved[2]),
                                 setattr(ticmap, "fetch_src", saved[3])))
        _, tic, fwd, rev, _, _ = small_data()
        ticmap.fetch_tic = lambda ids, d, o=False: (tic, {})
        ticmap.fetch_dr2n = lambda ids, d, o=False: (fwd, {})
        ticmap.fetch_rev = lambda ids, d, o=False: (rev, {})

        def broken(ids, d, o=False):
            raise ticmap.httpcache.FetchError("the archive is down")

        ticmap.fetch_src = broken
        with self.assertRaises(ticmap.httpcache.FetchError):
            ticmap.fetch_all([1, 2, 3], self.root, self.snap)
        after = {n: file_bytes(os.path.join(self.snap, n)) for n in before}
        self.assertEqual(before, after)
        ticmap.load_snapshots(self.snap)  # still a consistent set

    def test_build_from_a_damaged_folder_says_why_and_exits_with_1(self):
        import contextlib
        import io
        self.write()
        with open(os.path.join(self.snap, "tic_records.csv"), "a") as fh:
            fh.write("# edited by hand\n")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = ticmap.main(["build", "--snap-dir", self.snap,
                                "--out", os.path.join(self.root, "t.csv")])
        self.assertEqual(code, 1)
        self.assertIn("tic_records.csv", err.getvalue())
        self.assertFalse(os.path.exists(os.path.join(self.root, "t.csv")))

    def test_command_line_reports_a_failed_download_and_exits_with_1(self):
        targets = os.path.join(self.root, "t.txt")
        with open(targets, "w") as fh:
            fh.write("1\n")
        saved = ticmap.fetch_all

        def broken(*a, **k):
            raise ticmap.httpcache.FetchError("the archive is down")

        ticmap.fetch_all = broken
        self.addCleanup(setattr, ticmap, "fetch_all", saved)
        import contextlib
        import io
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = ticmap.main(["fetch", "--targets", targets, "--snap-dir", self.snap,
                                "--data-dir", self.root])
        self.assertEqual(code, 1)
        self.assertIn("Run the same command again", err.getvalue())


def file_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


class CommittedTableTests(unittest.TestCase):
    """The committed table must be reproducible from the committed snapshots."""

    def test_rebuild_gives_the_same_file(self):
        snap = os.path.join(ROOT, "snapshots")
        table = os.path.join(ROOT, "tic_to_gaia_dr3.csv")
        if not (os.path.isdir(snap) and os.path.exists(table)):
            self.skipTest("snapshots or table not present")
        tmp = tempfile.mkdtemp()
        try:
            out = os.path.join(tmp, "rebuilt.csv")
            ticmap.build_all(snap, out)
            self.assertTrue(filecmp.cmp(out, table, shallow=False))
            self.assertTrue(filecmp.cmp(os.path.join(tmp, "rebuilt.meta.json"),
                                        os.path.join(ROOT, "tic_to_gaia_dr3.meta.json"),
                                        shallow=False))
        finally:
            shutil.rmtree(tmp)

    def test_one_row_per_target(self):
        table = os.path.join(ROOT, "tic_to_gaia_dr3.csv")
        snap = os.path.join(ROOT, "snapshots", "target_ids.txt")
        if not (os.path.exists(table) and os.path.exists(snap)):
            self.skipTest("table not present")
        rows = ticmap.read_csv_dicts(table)
        with open(snap) as fh:
            ids = [int(x) for x in fh.read().split()]
        self.assertEqual([int(r["tic"]) for r in rows], sorted(ids))
        self.assertEqual(len({r["tic"] for r in rows}), len(rows))


if __name__ == "__main__":
    unittest.main()
