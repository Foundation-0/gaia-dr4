"""Tests for gaia_datalink.py. They send nothing to the Gaia archive.

Run from this folder:  python3 -m unittest -v

Some tests start a small web server on 127.0.0.1 that pretends to be the archive.
That server counts how many requests are open at the same moment, which is how the
"never more than N jobs" rule is checked.
"""
import contextlib
import csv
import gzip
import http.server
import io
import json
import logging
import os
import tarfile
import tempfile
import threading
import time
import unittest
import unittest.mock as mock
import urllib.parse
import zipfile

import gaia_datalink as g

logging.disable(logging.CRITICAL)  # keep the test output short
HERE = os.path.dirname(os.path.abspath(__file__))
DR3 = g.PROFILES["Gaia DR3"]


# ---- helpers that build archive-like answers --------------------------------

def csv_bytes(sid, n=12, t0=1700.0):
    """A DATAMODEL_STANDARD file for one source, shaped like the archive's."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(g._DR3_COLUMNS)
    for i in range(n):
        t = t0 + 10.0 * i
        row = {c: "" for c in g._DR3_COLUMNS}
        row.update(solution_id="375316653866487564", source_id=sid, transit_id=str(1000 + i),
                   g_transit_time=repr(t), g_transit_flux="5000.5", g_transit_flux_error="3.2",
                   g_transit_flux_over_error="1500.0", g_transit_mag="15.1",
                   bp_obs_time=repr(t + 0.0003), bp_flux="2000.0", bp_mag="15.6",
                   rp_obs_time=repr(t + 0.0004), rp_flux="3000.0", rp_mag="14.5",
                   variability_flag_g_reject="false", rejected_by_photometry="false")
        w.writerow([row[c] for c in g._DR3_COLUMNS])
    return buf.getvalue().encode()


def gaia_bytes(sids, n=7):
    """A DATAMODEL_GAIA answer: one row per source, arrays in the cells."""
    cols = g._DR3_GAIA_COLUMNS
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    for sid in sids:
        arr = lambda f: "(" + ", ".join(f(i) for i in range(n)) + ")"
        vals = {"solution_id": "1", "source_id": sid, "n_transits": str(n),
                "transit_id": arr(lambda i: str(100 + i)), "g_transit_time": arr(lambda i: repr(1700.0 + i)),
                "g_transit_flux": arr(lambda i: "1.0"), "g_transit_mag": arr(lambda i: "15.0"),
                "bp_obs_time": arr(lambda i: repr(1700.0 + i)), "bp_flux": arr(lambda i: "1.0"),
                "bp_mag": arr(lambda i: "15.5"), "rp_obs_time": arr(lambda i: "NaN" if i == 2 else repr(1700.0 + i)),
                "rp_flux": arr(lambda i: "1.0"), "rp_mag": arr(lambda i: "NaN" if i == 2 else "14.5")}
        w.writerow([vals[c] for c in cols])
    return buf.getvalue().encode()


def zip_bytes(sids):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for sid in sids:
            z.writestr("EPOCH_PHOTOMETRY_Gaia_DR3_%s.csv" % sid, csv_bytes(sid))
    return buf.getvalue()


def tgz_bytes(sids):
    """The same files as a tar archive inside a gzip file (what ESA's user guide describes)."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for sid in sids:
            data = csv_bytes(sid)
            info = tarfile.TarInfo("EPOCH_PHOTOMETRY_Gaia_DR3_%s.csv" % sid)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def good_answer(ids, missing=()):
    """What the archive sends for `ids`, leaving out sources in `missing` (they have no data)."""
    have = [i for i in ids if i not in missing]
    if not have:
        return g.Response(200, {"content-type": "text/csv"}, b"")
    if len(ids) == 1:
        return g.Response(200, {"content-type": "text/csv"}, csv_bytes(have[0]))
    return g.Response(200, {"content-type": "application/zip"}, zip_bytes(have))


def error_page(message, status=500):
    html = ("<html><head><style>body{color:black}</style></head><body><h2>SERVICE ERROR</h2>"
            "<h2>SERVICE ERROR - %d</h2><h3>Description</h3><ul><li>Context: DataRetrieval</li>"
            "<li>Message: %s</li><li>Cannot process request: 'https://example.invalid/x' (req: Reqid: "
            "anonymous-0123-abcd, retrieval access: DIRECT), for user: UwsJobOwner{id='anonymous', "
            "ip='203.0.113.9', session='ABCDEF'}</li></ul></body></html>") % (status, message)
    return g.Response(status, {"content-type": "text/html;charset=UTF-8"}, html.encode())


class FakeTransport:
    """Stands in for the network. `handler(ids, call_number)` returns a Response."""

    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def get(self, url):
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        ids = q["ID"][0].split(",")
        self.calls.append(ids)
        return self.handler(ids, len(self.calls))


class FixedRng:
    """random() always 1.0, so backoff delays are exactly base * 2**(attempt-1)."""

    def random(self):
        return 1.0


def make_fetcher(tmp, handler, **kw):
    cfg_args = dict(min_interval=0.0, jobs=1, batch_size=5)
    cfg_args.update(kw)
    sleeps = []
    f = g.Fetcher(g.Config(tmp, **cfg_args), transport=FakeTransport(handler),
                  sleep=lambda s: sleeps.append(s), rng=FixedRng())
    f.sleeps = sleeps
    return f


def events(tmp, kind=None):
    with open(os.path.join(tmp, "events.jsonl")) as fh:
        ev = [json.loads(line) for line in fh]
    return [e for e in ev if kind is None or e["event"] == kind]


IDS = ["1001", "1002", "1003", "1004", "1005"]


# ---- reading answers ---------------------------------------------------------

class TestClassify(unittest.TestCase):
    def test_retry_after_seconds_and_date(self):
        self.assertEqual(g.parse_retry_after("7"), 7.0)
        self.assertEqual(g.parse_retry_after(None), 0.0)
        self.assertEqual(g.parse_retry_after("soon"), 0.0)
        future = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(time.time() + 100))
        self.assertTrue(90 < g.parse_retry_after(future) <= 100)

    def test_empty_200_means_no_data(self):
        self.assertEqual(g.classify(g.Response(200, {"content-type": "text/csv"}, b"")).kind, "empty")

    def test_html_with_200_is_not_data(self):
        r = g.Response(200, {"content-type": "text/html"}, b"<html><body>maintenance</body></html>")
        self.assertEqual(g.classify(r).kind, "retry")

    def test_messages_seen_on_the_live_archive(self):
        # The wording below was returned by the live archive on 27 Oct 2026 (HTTP 500 for all of them).
        old = g.classify(error_page("The 'INDIVIDUAL' data structure has been deprecated - use 'DATAMODEL_STANDARD' instead"))
        self.assertEqual(old.kind, "fatal")
        bad = g.classify(error_page("Invalid Data Structure parameter: 'FOO', valid ones are: DATAMODEL_GAIA, DATAMODEL_STANDARD"))
        self.assertEqual(bad.kind, "fatal")
        many = g.classify(error_page("Maximum number of Source Ids reached (max: 50, found: 51)"))
        self.assertEqual((many.kind, many.limit), ("too_many", 50))
        dr4 = g.classify(error_page("No services found for Reqid: anonymous-1, retrieval access: DIRECT, SOURCE_ID and Gaia DR4"))
        self.assertEqual(dr4.kind, "fatal")

    def test_status_codes(self):
        h = {"content-type": "text/plain"}
        self.assertEqual(g.classify(g.Response(429, dict(h, **{"retry-after": "30"}), b"slow down")).retry_after, 30.0)
        for status in (500, 502, 503, 504, 408):
            self.assertEqual(g.classify(g.Response(status, h, b"oops")).kind, "retry", status)
        for status in (401, 403):
            self.assertEqual(g.classify(g.Response(status, h, b"no")).kind, "fatal", status)
        self.assertEqual(g.classify(g.Response(404, h, b"no")).kind, "fail")

    def test_queue_message_waits_longer(self):
        r = g.classify(g.Response(503, {}, b"The queue of this user is full"))
        self.assertEqual(r.kind, "queue")

    def test_error_page_hides_address_and_session(self):
        msg = g.page_message(error_page("Linking parameter is null").body)
        self.assertEqual(msg, "Linking parameter is null")
        raw = g.page_message(b"<html>ip='203.0.113.9' session='ABC' Reqid: anonymous-abc-123</html>")
        self.assertNotIn("203.0.113.9", raw)
        self.assertNotIn("ABC", raw)

    def test_real_saved_error_page_if_present(self):
        path = os.path.join(HERE, "data", "probe", "single_ds_INDIVIDUAL.body")
        if not os.path.exists(path):
            self.skipTest("no saved live answer (run probe.py first)")
        with open(path, "rb") as f:
            resp = g.Response(500, {"content-type": "text/html"}, f.read())
        out = g.classify(resp)
        self.assertEqual(out.kind, "fatal")
        self.assertIn("DATAMODEL_STANDARD", out.message)
        self.assertNotRegex(out.message, r"\d+\.\d+\.\d+\.\d+")


# ---- checking files ----------------------------------------------------------

class TestChecks(unittest.TestCase):
    def test_good_file(self):
        info = g.check_standard_csv(csv_bytes("42", n=12), "42", DR3)
        self.assertEqual(info["rows"], 12)
        self.assertEqual(info["n_g"], 12)
        self.assertEqual(info["t_first"], 1700.0)

    def test_empty_bp_values_are_fine(self):
        text = csv_bytes("42").decode().replace("15.6", "").replace("2000.0", "")
        self.assertEqual(g.check_standard_csv(text.encode(), "42", DR3)["rows"], 12)

    def test_failures(self):
        good = csv_bytes("42").decode()
        cases = {
            "cut off": good[:-7],
            "no rows": good.split("\n")[0] + "\n",
            "wrong source": csv_bytes("43").decode(),
            "missing column": good.replace("g_transit_mag", "g_transit_mugg", 1),
            "time out of range": good.replace("1700.0", "5000.0", 1),
            "not a number": good.replace("5000.5", "abc", 1),
            "time not a number": good.replace("1700.0", "abc", 1),
            "bad magnitude": good.replace("15.1", "99.0", 1),
            "short row": good.replace(",15.1,", ",", 1),
        }
        for name, text in cases.items():
            with self.assertRaises(g.ValidationError, msg=name):
                g.check_standard_csv(text.encode(), "42", DR3)

    def test_too_many_rows(self):
        with self.assertRaises(g.ValidationError):
            g.check_standard_csv(csv_bytes("42", n=3001), "42", DR3)

    def test_duplicate_transit_id(self):
        text = csv_bytes("42").decode().replace(",1001,", ",1002,", 1)
        with self.assertRaises(g.ValidationError):
            g.check_standard_csv(text.encode(), "42", DR3)

    def test_gaia_row(self):
        header, rows = g.split_gaia(gaia_bytes(["7", "8"]))
        info = g.check_gaia_row(header, rows["7"], "7", DR3)
        self.assertEqual(info["rows"], 7)
        bad = list(rows["7"])
        bad[header.index("g_transit_mag")] = "(15.0, 15.0)"
        with self.assertRaises(g.ValidationError):
            g.check_gaia_row(header, bad, "7", DR3)

    def test_split_standard_zip_and_plain(self):
        self.assertEqual(sorted(g.split_standard(zip_bytes(["5", "6"]), "DATAMODEL_STANDARD")), ["5", "6"])
        self.assertEqual(list(g.split_standard(csv_bytes("9"), "DATAMODEL_STANDARD")), ["9"])

    def test_split_standard_gzip_and_tar_gzip(self):
        # Not seen on the live archive, which sends zip. ESA's user guide says .gzip.
        self.assertEqual(list(g.split_standard(gzip.compress(csv_bytes("9")), "DATAMODEL_STANDARD")), ["9"])
        self.assertEqual(sorted(g.split_standard(tgz_bytes(["5", "6"]), "DATAMODEL_STANDARD")), ["5", "6"])

    def test_damaged_or_oversized_gzip(self):
        good = gzip.compress(csv_bytes("9"))
        with self.assertRaises(g.ValidationError):
            g.unpack_answer(good[:-12])  # cut off
        with self.assertRaises(g.ValidationError):
            g.unpack_answer(good[:10] + b"\x00" * 30)  # not gzip data after the header
        with mock.patch.object(g, "MAX_UNPACKED", 1000):
            with self.assertRaises(g.ValidationError):
                g.unpack_answer(good)
            with self.assertRaises(g.ValidationError):
                g.unpack_answer(zip_bytes(["5"]))

    def test_gaia_row_in_gzip(self):
        header, rows = g.split_gaia(gzip.compress(gaia_bytes(["7"])))
        self.assertEqual(list(rows), ["7"])
        with self.assertRaises(g.ValidationError):
            g.split_gaia(zip_bytes(["5", "6"]))

    def test_zip_member_name_must_match_content(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("EPOCH_PHOTOMETRY_Gaia_DR3_111.csv", csv_bytes("222"))
        with self.assertRaises(g.ValidationError):
            g.split_standard(buf.getvalue(), "DATAMODEL_STANDARD")

    def test_damaged_zip(self):
        with self.assertRaises(g.ValidationError):
            g.split_standard(zip_bytes(["5"])[:-30], "DATAMODEL_STANDARD")


class TestConfigAndIds(unittest.TestCase):
    def test_jobs_never_above_five(self):
        for jobs in (0, 6, 50):
            with self.assertRaises(ValueError):
                g.Config("x", jobs=jobs)
            with self.assertRaises(ValueError):
                g.SlotPool(jobs)
        self.assertEqual(g.Config("x", jobs=5).jobs, 5)

    def test_old_structure_names_are_refused_with_the_new_name(self):
        with self.assertRaisesRegex(ValueError, "DATAMODEL_STANDARD"):
            g.Config("x", structure="INDIVIDUAL")
        with self.assertRaisesRegex(ValueError, "DATAMODEL_GAIA"):
            g.Config("x", structure="RAW")

    def test_batch_size_limit(self):
        with self.assertRaises(ValueError):
            g.Config("x", batch_size=51)
        self.assertEqual(g.Config("x", batch_size=5000, max_ids=g.SIGNED_IN_MAX_IDS).batch_size, 5000)

    def test_dr4_profile_is_marked_unverified_and_has_no_gaia_layout(self):
        self.assertIn("UNVERIFIED", g.PROFILES["Gaia DR4"].note)
        with self.assertRaises(ValueError):
            g.Config("x", release="Gaia DR4", structure="DATAMODEL_GAIA")
        self.assertEqual(g.Config("x", release="Gaia DR4").release, "Gaia DR4")

    def test_dr4_draft_column_names_are_checked(self):
        dr4 = g.PROFILES["Gaia DR4"]
        text = csv_bytes("42").decode()
        for old, new in (("g_transit_time", "g_obs_time"), ("g_transit_flux", "g_flux"), ("g_transit_mag", "g_mag")):
            text = text.replace(old, new)
        self.assertEqual(g.check_standard_csv(text.encode(), "42", dr4)["n_g"], 12)
        with self.assertRaises(g.ValidationError):  # DR3 names are not DR4 names
            g.check_standard_csv(csv_bytes("42"), "42", dr4)

    def test_format_and_release(self):
        with self.assertRaises(ValueError):
            g.Config("x", fmt="FITS")
        with self.assertRaises(ValueError):
            g.Config("x", release="Gaia DR9")

    def test_read_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "ids.txt")
            with open(p, "w") as f:
                f.write("# comment\n123\nGaia DR3 456\n\n123\n 789 \n")
            self.assertEqual(g.read_ids(p), ["123", "456", "789"])
            with open(p, "w") as f:
                f.write("name,source_id\nA,111\nB,222\n")
            self.assertEqual(g.read_ids(p), ["111", "222"])
            with open(p, "w") as f:
                f.write("source_id\n5\n6\n")
            self.assertEqual(g.read_ids(p), ["5", "6"])
            for bad in ("12abc\n", "0\n", "99999999999999999999\n", "name,x\nA,1\n"):
                with open(p, "w") as f:
                    f.write(bad)
                with self.assertRaises(ValueError, msg=bad):
                    g.read_ids(p)

    def test_cli_refuses_old_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            ids = os.path.join(tmp, "ids.txt")
            with open(ids, "w") as fh:
                fh.write("1\n")
            out = os.path.join(tmp, "o")
            with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(g.main(["fetch", ids, "--out", out, "--structure", "RAW"]), 3)
                self.assertEqual(g.main(["fetch", ids, "--out", out, "--jobs", "6"]), 3)
                self.assertEqual(g.main(["fetch", ids, "--out", out, "--dry-run"]), 0)


class TestExitCodes(unittest.TestCase):
    """main() returns 0 (all done), 2 (some failed), 3 (cannot succeed), 4 (stopped early)."""

    def run_main(self, handler, *extra):
        class T:
            def __init__(self, *a, **k):
                self.fake = FakeTransport(handler)

            def get(self, url):
                return self.fake.get(url)
        with tempfile.TemporaryDirectory() as tmp:
            ids = os.path.join(tmp, "ids.txt")
            with open(ids, "w") as fh:
                fh.write("1001\n1002\n")
            args = ["fetch", ids, "--out", os.path.join(tmp, "o"), "--min-interval", "0", "--slots-dir",
                    os.path.join(tmp, "slots")] + list(extra)
            with mock.patch.object(g, "Transport", T), contextlib.redirect_stderr(io.StringIO()), \
                    contextlib.redirect_stdout(io.StringIO()):
                code = g.main(args)
            logging.getLogger("gaia_datalink").handlers.clear()
            return code

    def test_all_done(self):
        self.assertEqual(self.run_main(lambda ids, n: good_answer(ids)), 0)

    def test_no_data_is_not_a_failure(self):
        self.assertEqual(self.run_main(lambda ids, n: good_answer(ids, missing={"1001"})), 0)

    def test_no_second_look_flag(self):
        calls = []

        def handler(ids, n):
            calls.append(ids)
            return good_answer(ids, missing={"1001"})
        self.assertEqual(self.run_main(handler, "--no-second-look"), 0)
        self.assertEqual(len(calls), 1)
        calls.clear()
        self.assertEqual(self.run_main(handler), 0)
        self.assertEqual(len(calls), 2)

    def test_fatal(self):
        code = self.run_main(lambda ids, n: error_page("The 'RAW' data structure has been deprecated - use 'DATAMODEL_GAIA' instead"))
        self.assertEqual(code, 3)

    def test_some_failed(self):
        def handler(ids, n):
            return g.Response(400, {}, b"bad") if "1001" in ids else good_answer(ids)
        self.assertEqual(self.run_main(handler, "--batch-size", "1"), 2)

    def test_stopped_early(self):
        self.assertEqual(self.run_main(lambda ids, n: good_answer(ids), "--batch-size", "1", "--max-requests", "1"), 4)


# ---- the fetcher, with a scripted fake archive -------------------------------

class TestFetcher(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_all_good(self):
        f = make_fetcher(self.tmp, lambda ids, n: good_answer(ids))
        s = f.run(IDS)
        self.assertEqual((s["ok"], s["no_data"], s["failed"], s["requests"]), (5, 0, 0, 1))
        self.assertEqual(s["rows"], 60)
        for sid in IDS:
            self.assertTrue(os.path.exists(os.path.join(self.tmp, "Gaia_DR3", "DATAMODEL_STANDARD", sid + ".csv")))
        self.assertEqual(g.check_run(self.tmp, "Gaia DR3", "DATAMODEL_STANDARD")["files_ok"], 5)

    def test_log_has_source_structure_date_and_response(self):
        make_fetcher(self.tmp, lambda ids, n: good_answer(ids)).run(IDS)
        src = events(self.tmp, "source")[0]
        for key in ("source_id", "structure", "release", "t", "http_status", "sha256", "status", "bytes"):
            self.assertIn(key, src)
        self.assertEqual(src["structure"], "DATAMODEL_STANDARD")
        self.assertRegex(src["t"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        req = events(self.tmp, "request")[0]
        self.assertEqual(req["http_status"], 200)
        self.assertEqual(req["ids"], IDS)

    def test_missing_member_gets_a_second_look_before_it_is_no_data(self):
        f = make_fetcher(self.tmp, lambda ids, n: good_answer(ids, missing={"1003"}))
        s = f.run(IDS)
        self.assertEqual((s["ok"], s["no_data"], s["requests"]), (4, 1, 2))
        self.assertEqual(f.transport.calls, [IDS, ["1003"]])
        no_data = [e for e in events(self.tmp, "source") if e["status"] == "no_data"]
        self.assertEqual([e["source_id"] for e in no_data], ["1003"])
        self.assertIn("second time", no_data[0]["message"])
        self.assertEqual([r["second_look"] for r in events(self.tmp, "request")], [False, True])

    def test_missing_member_that_turns_up_on_the_second_look_is_kept(self):
        f = make_fetcher(self.tmp, lambda ids, n: good_answer(ids, missing={"1003"} if n == 1 else ()))
        s = f.run(IDS)
        self.assertEqual((s["ok"], s["no_data"], s["requests"]), (5, 0, 2))

    def test_second_look_can_be_switched_off(self):
        f = make_fetcher(self.tmp, lambda ids, n: good_answer(ids, missing={"1003"}), confirm_missing=False)
        s = f.run(IDS)
        self.assertEqual((s["ok"], s["no_data"], s["requests"]), (4, 1, 1))

    def test_second_look_is_made_once_only(self):
        # Two sources absent every time: one extra request for both, not a loop.
        f = make_fetcher(self.tmp, lambda ids, n: good_answer(ids, missing={"1002", "1004"}))
        s = f.run(IDS)
        self.assertEqual((s["ok"], s["no_data"], s["requests"]), (3, 2, 2))
        self.assertEqual(f.transport.calls[1], ["1002", "1004"])

    def test_gzip_and_tar_gzip_answers_are_accepted(self):
        def handler(ids, n):
            if len(ids) == 1:
                return g.Response(200, {"content-type": "application/gzip"}, gzip.compress(csv_bytes(ids[0])))
            return g.Response(200, {"content-type": "application/gzip"}, tgz_bytes(ids))
        s = make_fetcher(self.tmp, handler).run(IDS)
        self.assertEqual((s["ok"], s["requests"]), (5, 1))
        self.assertEqual(g.check_run(self.tmp, "Gaia DR3", "DATAMODEL_STANDARD")["files_ok"], 5)

    def test_empty_answer_is_asked_twice_before_no_data(self):
        f = make_fetcher(self.tmp, lambda ids, n: good_answer(ids, missing=set(ids)))
        s = f.run(IDS)
        self.assertEqual((s["no_data"], s["requests"]), (5, 2))
        self.assertIn("twice", events(self.tmp, "source")[0]["message"])

    def test_empty_then_data_on_the_second_ask(self):
        f = make_fetcher(self.tmp, lambda ids, n: good_answer(ids, missing=set(ids) if n == 1 else ()))
        s = f.run(IDS)
        self.assertEqual((s["ok"], s["no_data"], s["requests"]), (5, 0, 2))

    def test_resume_sends_nothing(self):
        make_fetcher(self.tmp, lambda ids, n: good_answer(ids, missing={"1002"})).run(IDS)
        f2 = make_fetcher(self.tmp, lambda ids, n: self.fail("should not ask again"))
        s = f2.run(IDS)
        self.assertEqual((s["requests"], s["already_done_before_run"]), (0, 5))

    def test_resume_asks_again_for_failed_and_for_deleted_files(self):
        make_fetcher(self.tmp, lambda ids, n: good_answer(ids)).run(IDS)
        os.remove(os.path.join(self.tmp, "Gaia_DR3", "DATAMODEL_STANDARD", "1004.csv"))
        f2 = make_fetcher(self.tmp, lambda ids, n: good_answer(ids))
        s = f2.run(IDS)
        self.assertEqual((s["ok"], s["requests"]), (1, 1))
        self.assertEqual(f2.transport.calls, [["1004"]])

    def test_retry_no_data_flag(self):
        make_fetcher(self.tmp, lambda ids, n: good_answer(ids, missing={"1002"})).run(IDS)
        f2 = make_fetcher(self.tmp, lambda ids, n: good_answer(ids), retry_no_data=True)
        self.assertEqual(f2.run(IDS)["ok"], 1)

    def test_429_waits_at_least_retry_after(self):
        def handler(ids, n):
            if n == 1:
                return g.Response(429, {"retry-after": "37"}, b"Too many requests")
            return good_answer(ids)
        f = make_fetcher(self.tmp, handler)
        s = f.run(IDS)
        self.assertEqual((s["ok"], s["requests"]), (5, 2))
        self.assertAlmostEqual(max(f.sleeps), 37.0, delta=0.5)  # Retry-After beats the 2 s backoff

    def test_5xx_backoff_doubles_and_is_capped(self):
        f = make_fetcher(self.tmp, lambda ids, n: g.Response(503, {}, b"busy"), batch_size=1,
                         max_attempts=6, backoff_base=2.0, backoff_cap=20.0)
        s = f.run(["1001"])
        self.assertEqual((s["failed"], s["requests"]), (1, 6))
        self.assertEqual(len(f.sleeps), 5)
        for got, want in zip(f.sleeps, [2.0, 4.0, 8.0, 16.0, 20.0]):
            self.assertAlmostEqual(got, want, delta=0.2)
        self.assertIn("gave up after 6 attempts", events(self.tmp, "source")[0]["message"])

    def test_recovers_after_5xx(self):
        f = make_fetcher(self.tmp, lambda ids, n: g.Response(502, {}, b"bad gateway") if n < 2 else good_answer(ids))
        s = f.run(IDS)
        self.assertEqual((s["ok"], s["requests"]), (5, 2))

    def test_second_failure_splits_the_batch(self):
        f = make_fetcher(self.tmp, lambda ids, n: g.Response(502, {}, b"bad gateway") if n < 3 else good_answer(ids))
        s = f.run(IDS)
        self.assertEqual(s["ok"], 5)
        self.assertEqual([len(c) for c in f.transport.calls], [5, 5, 2, 3])

    def test_network_error_is_retried(self):
        state = {"n": 0}

        def handler(ids, n):
            state["n"] += 1
            if state["n"] == 1:
                raise g.TransportError("timeout")
            return good_answer(ids)
        s = make_fetcher(self.tmp, handler).run(IDS)
        self.assertEqual((s["ok"], s["requests"]), (5, 2))

    def test_too_many_ids_splits_and_remembers_the_limit(self):
        def handler(ids, n):
            if len(ids) > 3:
                return error_page("Maximum number of Source Ids reached (max: 3, found: %d)" % len(ids))
            return good_answer(ids)
        f = make_fetcher(self.tmp, handler, batch_size=5)
        s = f.run(["%d" % (2000 + i) for i in range(10)])
        self.assertEqual(s["ok"], 10)
        self.assertEqual(f.max_ids, 3)
        self.assertTrue(all(len(c) <= 3 for c in f.transport.calls[1:]), f.transport.calls)
        self.assertEqual(len(f.transport.calls), 5)  # one rejected request, then 3+2 and 3+2

    def test_old_structure_name_message_stops_the_run_at_once(self):
        f = make_fetcher(self.tmp, lambda ids, n: error_page("The 'INDIVIDUAL' data structure has been deprecated - use 'DATAMODEL_STANDARD' instead"))
        s = f.run(IDS)
        self.assertEqual(s["requests"], 1)
        self.assertIsInstance(s["error"], g.FatalError)
        self.assertEqual(s["ok"], 0)

    def test_one_bad_source_is_found_by_splitting(self):
        def handler(ids, n):
            if "1003" in ids:
                return error_page("something broke inside the archive")
            return good_answer(ids)
        f = make_fetcher(self.tmp, handler, max_attempts=3, split_after=2, abort_after=100)
        s = f.run(IDS)
        self.assertEqual((s["ok"], s["failed"]), (4, 1))
        failed = [e for e in events(self.tmp, "source") if e["status"] == "failed"]
        self.assertEqual([e["source_id"] for e in failed], ["1003"])

    def test_invalid_file_is_kept_aside_and_asked_for_again(self):
        def handler(ids, n):
            if n == 1:
                return g.Response(200, {"content-type": "text/csv"}, csv_bytes(ids[0])[:-40])  # cut off
            return good_answer(ids)
        f = make_fetcher(self.tmp, handler, batch_size=1)
        s = f.run(["1001"])
        self.assertEqual((s["ok"], s["requests"]), (1, 2))
        self.assertEqual(len(os.listdir(os.path.join(self.tmp, "rejected"))), 1)

    def test_one_invalid_member_does_not_lose_the_others(self):
        def handler(ids, n):
            if n == 1:
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w") as z:
                    for sid in ids:
                        data = csv_bytes(sid)
                        if sid == "1002":
                            data = data.replace(b"1700.0", b"9999.0", 1)
                        z.writestr("EPOCH_PHOTOMETRY_Gaia_DR3_%s.csv" % sid, data)
                return g.Response(200, {"content-type": "application/zip"}, buf.getvalue())
            return good_answer(ids)
        f = make_fetcher(self.tmp, handler)
        s = f.run(IDS)
        self.assertEqual((s["ok"], s["requests"]), (5, 2))
        self.assertEqual(f.transport.calls[1], ["1002"])

    def test_unexpected_source_in_answer_is_rejected(self):
        f = make_fetcher(self.tmp, lambda ids, n: good_answer(["1001", "9999"]) if n == 1 else good_answer(ids),
                         batch_size=2)
        s = f.run(["1001", "1002"])
        self.assertEqual(s["ok"], 2)
        self.assertGreater(s["requests"], 1)

    def test_service_looks_down_stops_the_run(self):
        f = make_fetcher(self.tmp, lambda ids, n: g.Response(503, {}, b"down"), batch_size=1, abort_after=4)
        s = f.run(["%d" % (3000 + i) for i in range(10)])
        self.assertEqual(s["requests"], 4)
        self.assertIsInstance(s["error"], g.Aborted)
        self.assertEqual(s["not_attempted"] + s["failed"], 10)

    def test_max_requests(self):
        f = make_fetcher(self.tmp, lambda ids, n: good_answer(ids), batch_size=1, max_requests=3)
        s = f.run(["%d" % (4000 + i) for i in range(10)])
        self.assertEqual((s["requests"], s["ok"]), (3, 3))
        self.assertIsInstance(s["error"], g.Aborted)

    def test_gaia_structure(self):
        def handler(ids, n):
            have = [i for i in ids if i != "1003"]
            return g.Response(200, {"content-type": "text/csv"}, gaia_bytes(have))
        f = make_fetcher(self.tmp, handler, structure="DATAMODEL_GAIA")
        s = f.run(IDS)
        self.assertEqual((s["ok"], s["no_data"]), (4, 1))
        self.assertEqual(g.check_run(self.tmp, "Gaia DR3", "DATAMODEL_GAIA")["files_ok"], 4)

    def test_request_url_uses_the_new_names(self):
        f = make_fetcher(self.tmp, lambda ids, n: good_answer(ids))
        url = f.build_url(["1", "2"])
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        self.assertEqual(q["DATA_STRUCTURE"], ["DATAMODEL_STANDARD"])
        self.assertEqual(q["RETRIEVAL_TYPE"], ["EPOCH_PHOTOMETRY"])
        self.assertEqual(q["RELEASE"], ["Gaia DR3"])
        self.assertEqual(q["ID"], ["1,2"])
        self.assertNotIn("INDIVIDUAL", url)

    def test_check_run_finds_damage(self):
        make_fetcher(self.tmp, lambda ids, n: good_answer(ids)).run(IDS)
        path = os.path.join(self.tmp, "Gaia_DR3", "DATAMODEL_STANDARD", "1002.csv")
        with open(path, "ab") as fh:
            fh.write(b"extra\n")
        res = g.check_run(self.tmp, "Gaia DR3", "DATAMODEL_STANDARD")
        self.assertEqual([p[0] for p in res["problems"]], ["1002"])

    def test_sign_in_refuses_other_hosts(self):
        class T:
            def post_form(self, url, fields):
                raise AssertionError("credentials must not be sent")
        for url in ("http://gea.esac.esa.int/data-server/login", "https://evil.example.com/login",
                    "https://esa.int.evil.example.com/login"):
            with self.assertRaises(g.FatalError):
                g.sign_in(T(), "u", "p", url=url)

    def test_sign_in_sends_form_to_esa(self):
        seen = {}

        class T:
            def post_form(self, url, fields):
                seen.update(url=url, fields=fields)
                return g.Response(200, {}, b"")
        g.sign_in(T(), "someone", "secret")
        self.assertEqual(seen["url"], g.LOGIN_URL)
        self.assertEqual(seen["fields"], {"username": "someone", "password": "secret"})


# ---- the job limit, measured at a pretend archive ------------------------------

class PretendArchive:
    """A local web server that answers like the archive and counts requests open at once."""

    def __init__(self, delay=0.15):
        outer = self
        self.delay = delay
        self.lock = threading.Lock()
        self.open = 0
        self.peak = 0
        self.total = 0

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                with outer.lock:
                    outer.open += 1
                    outer.peak = max(outer.peak, outer.open)
                    outer.total += 1
                try:
                    time.sleep(outer.delay)
                    q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                    ids = q["ID"][0].split(",")
                    r = good_answer(ids)
                    self.send_response(r.status)
                    self.send_header("Content-Type", r.headers["content-type"])
                    self.send_header("Content-Length", str(len(r.body)))
                    self.end_headers()
                    self.wfile.write(r.body)
                finally:
                    with outer.lock:
                        outer.open -= 1

            def log_message(self, *a):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = "http://127.0.0.1:%d/data" % self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.server.shutdown()
        self.server.server_close()


class TestJobLimit(unittest.TestCase):
    def run_with(self, jobs, n_batches, slots_dir=None):
        with tempfile.TemporaryDirectory() as tmp, PretendArchive() as archive:
            cfg = g.Config(tmp, jobs=jobs, batch_size=2, min_interval=0.0, base_url=archive.url, slots_dir=slots_dir)
            f = g.Fetcher(cfg)
            s = f.run(["%d" % (5000 + i) for i in range(2 * n_batches)])
            self.assertEqual(s["ok"], 2 * n_batches)
            return s, archive

    def test_never_more_open_than_jobs(self):
        for jobs, n in ((1, 4), (2, 8), (3, 12), (5, 25)):
            s, archive = self.run_with(jobs, n)
            self.assertLessEqual(archive.peak, jobs, "server saw more than %d at once" % jobs)
            self.assertLessEqual(s["peak_open_requests"], jobs)
            if jobs > 1:
                self.assertGreaterEqual(archive.peak, 2, "requests did not run in parallel")
            self.assertEqual(archive.total, n)

    def test_more_than_five_sources_with_five_jobs(self):
        # The issue's check: a run over more than 5 sources shows at most 5 jobs open at any time.
        s, archive = self.run_with(5, 30)
        self.assertLessEqual(archive.peak, 5)

    def test_two_fetchers_share_the_limit_through_lock_files(self):
        with tempfile.TemporaryDirectory() as slots, PretendArchive(delay=0.2) as archive:
            results = []

            def one(k):
                with tempfile.TemporaryDirectory() as tmp:
                    cfg = g.Config(tmp, jobs=2, batch_size=2, min_interval=0.0, base_url=archive.url, slots_dir=slots)
                    ids = ["%d" % (6000 + 1000 * k + i) for i in range(16)]
                    results.append(g.Fetcher(cfg).run(ids))
            threads = [threading.Thread(target=one, args=(k,)) for k in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual([r["ok"] for r in results], [16, 16])
            self.assertLessEqual(archive.peak, 2)

    def test_pool_blocks_instead_of_going_over(self):
        pool = g.SlotPool(2)
        inside = []
        gate = threading.Event()

        def hold():
            with pool.acquire():
                inside.append(1)
                gate.wait(2)
        ts = [threading.Thread(target=hold) for _ in range(4)]
        for t in ts:
            t.start()
        time.sleep(0.3)
        self.assertEqual(len(inside), 2)
        gate.set()
        for t in ts:
            t.join()
        self.assertEqual(len(inside), 4)
        self.assertEqual(pool.peak, 2)


if __name__ == "__main__":
    unittest.main()
