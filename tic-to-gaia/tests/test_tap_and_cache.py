import http.server
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpcache  # noqa: E402
import tap  # noqa: E402

VOTABLE = b"""<?xml version="1.0"?>
<VOTABLE version="1.4" xmlns="http://www.ivoa.net/xml/VOTable/v1.3"><RESOURCE type="results">
<TABLE><FIELD name="id" datatype="long"/><FIELD name="gaia" datatype="char" arraysize="*"/>
<FIELD name="pmra" datatype="float"/>
<DATA><TABLEDATA>
<TR><TD>1</TD><TD>1234567890123456789</TD><TD>-3.5</TD></TR>
<TR><TD>2</TD><TD></TD><TD></TD></TR>
</TABLEDATA></DATA></TABLE></RESOURCE></VOTABLE>"""


ERROR_VOTABLE = b"""<?xml version="1.0"?>
<VOTABLE version="1.4" xmlns="http://www.ivoa.net/xml/VOTable/v1.3"><RESOURCE type="results">
<INFO name="QUERY_STATUS" value="ERROR">Query failed: something broke</INFO>
</RESOURCE></VOTABLE>"""

EMPTY_VOTABLE = b"""<?xml version="1.0"?>
<VOTABLE version="1.4" xmlns="http://www.ivoa.net/xml/VOTable/v1.3"><RESOURCE type="results">
<INFO name="QUERY_STATUS" value="OK"/>
<TABLE><FIELD name="id" datatype="long"/><FIELD name="gaia" datatype="char" arraysize="*"/>
<DATA><TABLEDATA></TABLEDATA></DATA></TABLE></RESOURCE></VOTABLE>"""


class ParsingTests(unittest.TestCase):
    def test_votable_error_document_is_an_error(self):
        with self.assertRaises(ValueError) as ctx:
            tap.parse_votable(ERROR_VOTABLE)
        self.assertIn("something broke", str(ctx.exception))

    def test_check_votable(self):
        self.assertIsNone(tap.check_votable(VOTABLE, ["id", "gaia"]))
        self.assertIsNone(tap.check_votable(EMPTY_VOTABLE, ["id", "gaia"]))  # no rows is fine
        self.assertIn("lacks", tap.check_votable(VOTABLE, ["id", "nonsense"]))
        self.assertIn("error", tap.check_votable(ERROR_VOTABLE, ["id"]))
        self.assertIn("not a readable", tap.check_votable(b"<html>503</html", ["id"]))

    def test_votable(self):
        names, rows = tap.parse_votable(VOTABLE)
        self.assertEqual(names, ["id", "gaia", "pmra"])
        self.assertEqual(rows, [["1", "1234567890123456789", "-3.5"], ["2", "", ""]])

    def test_csv(self):
        names, rows = tap.parse_csv(b"a,b\n1,\n2,x\n")
        self.assertEqual(names, ["a", "b"])
        self.assertEqual(rows, [["1", ""], ["2", "x"]])

    def test_id_list_accepts_digits_only(self):
        self.assertEqual(tap.id_list([1, "22", 333]), "1,22,333")
        with self.assertRaises(ValueError):
            tap.id_list(["1; DROP TABLE x"])
        with self.assertRaises(ValueError):
            tap.id_list([])

    def test_batches(self):
        self.assertEqual([len(b) for b in tap.batches(range(250))], [100, 100, 50])


class Handler(http.server.BaseHTTPRequestHandler):
    calls = 0
    seen_agent = None
    flaky_failures_left = 0

    def do_POST(self):
        Handler.calls += 1
        Handler.seen_agent = self.headers.get("User-Agent")
        n = int(self.headers.get("Content-Length", 0))
        self.rfile.read(n)
        status = 200
        body = b"a,b\n1,2\n"
        if self.path == "/bad":
            body = b"<?xml version='1.0'?><error/>"
        elif self.path == "/flaky" and Handler.flaky_failures_left > 0:
            Handler.flaky_failures_left -= 1
            status, body = 503, b"busy"
        elif self.path == "/always503":
            status, body = 503, b"busy"
        elif self.path == "/notfound":
            status, body = 404, b"no such thing"
        elif self.path == "/votable_error":
            body = ERROR_VOTABLE
        elif self.path == "/votable_other_table":
            body = VOTABLE.replace(b'name="id"', b'name="other"')
        elif self.path == "/votable_empty":
            body = EMPTY_VOTABLE
        elif self.path == "/votable_ok":
            body = VOTABLE
        self.send_response(status)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class CacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        Handler.calls = 0
        Handler.flaky_failures_left = 0
        httpcache.MIN_GAP = 0
        self.pauses = []
        saved = (httpcache._sleep, httpcache.RETRY_PAUSES, tap.MAST_TIC_TAP)
        httpcache._sleep = self.pauses.append  # record the pauses instead of waiting
        self.addCleanup(lambda: (setattr(httpcache, "_sleep", saved[0]),
                                 setattr(httpcache, "RETRY_PAUSES", saved[1]),
                                 setattr(tap, "MAST_TIC_TAP", saved[2])))

    def tearDown(self):
        shutil.rmtree(self.dir)

    def url(self, path="/ok"):
        return "http://127.0.0.1:%d%s" % (self.port, path)

    def test_second_call_is_served_from_disk(self):
        b1, i1 = httpcache.fetch(self.dir, "k", self.url(), data={"q": "1"})
        b2, i2 = httpcache.fetch(self.dir, "k", self.url(), data={"q": "1"})
        self.assertEqual(b1, b2)
        self.assertFalse(i1["from_cache"])
        self.assertTrue(i2["from_cache"])
        self.assertEqual(Handler.calls, 1)

    def test_identifying_user_agent_and_log(self):
        httpcache.fetch(self.dir, "k", self.url(), data={"q": "1"})
        self.assertIn("Foundation0-gaia-dr4", Handler.seen_agent)
        with open(os.path.join(self.dir, "requests.log")) as fh:
            lines = [json.loads(x) for x in fh]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["status"], 200)

    def test_different_query_is_a_different_request(self):
        httpcache.fetch(self.dir, "k", self.url(), data={"q": "1"})
        httpcache.fetch(self.dir, "k", self.url(), data={"q": "2"})
        self.assertEqual(Handler.calls, 2)

    def test_offline_mode_refuses_to_fetch(self):
        with self.assertRaises(httpcache.FetchError):
            httpcache.fetch(self.dir, "k", self.url(), data={"q": "1"}, offline=True)
        self.assertEqual(Handler.calls, 0)

    def test_rejected_answer_is_not_cached(self):
        with self.assertRaises(httpcache.FetchError):
            tap.csv_query(self.dir, "k", self.url("/bad"), "SELECT 1")
        with self.assertRaises(httpcache.FetchError):
            tap.csv_query(self.dir, "k", self.url("/bad"), "SELECT 1")
        self.assertEqual(Handler.calls, 2)  # asked again, nothing was saved

    def log_lines(self):
        with open(os.path.join(self.dir, "requests.log")) as fh:
            return [json.loads(x) for x in fh]

    def test_temporary_failure_is_tried_again_and_every_try_is_logged(self):
        Handler.flaky_failures_left = 2
        httpcache.RETRY_PAUSES = (10, 30)
        body, info = httpcache.fetch(self.dir, "k", self.url("/flaky"), data={"q": "1"})
        self.assertEqual(body, b"a,b\n1,2\n")
        self.assertEqual(Handler.calls, 3)
        self.assertEqual([x["status"] for x in self.log_lines()], [503, 503, 200])
        self.assertEqual([p for p in self.pauses if p >= 10], [10, 30])  # the pauses grow

    def test_gives_up_after_the_last_try_and_saves_nothing(self):
        with self.assertRaises(httpcache.FetchError):
            httpcache.fetch(self.dir, "k", self.url("/always503"), data={"q": "1"})
        self.assertEqual(Handler.calls, httpcache.RETRIES + 1)
        with self.assertRaises(httpcache.FetchError):
            httpcache.fetch(self.dir, "k", self.url("/always503"), data={"q": "1"}, offline=True)

    def test_a_final_error_is_not_tried_again(self):
        with self.assertRaises(httpcache.FetchError):
            httpcache.fetch(self.dir, "k", self.url("/notfound"), data={"q": "1"})
        self.assertEqual(Handler.calls, 1)

    def test_a_refused_connection_is_tried_again(self):
        import socket
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()  # nothing listens on this port now
        with self.assertRaises(httpcache.FetchError):
            httpcache.fetch(self.dir, "k", "http://127.0.0.1:%d/x" % port, data={"q": "1"})
        self.assertEqual(len(self.log_lines()), httpcache.RETRIES + 1)

    def test_mast_error_document_is_refused_and_not_saved(self):
        tap.MAST_TIC_TAP = self.url("/votable_error")
        for _ in range(2):
            with self.assertRaises(httpcache.FetchError):
                tap.mast_query(self.dir, "tic", "SELECT 1", require=["id", "gaia"])
        self.assertEqual(Handler.calls, 2)  # asked again: nothing was saved

    def test_mast_answer_without_the_wanted_columns_is_refused(self):
        tap.MAST_TIC_TAP = self.url("/votable_other_table")
        with self.assertRaises(httpcache.FetchError):
            tap.mast_query(self.dir, "tic", "SELECT 1", require=["id", "gaia"])

    def test_mast_table_with_the_columns_and_no_rows_is_accepted(self):
        tap.MAST_TIC_TAP = self.url("/votable_empty")
        names, rows, _ = tap.mast_query(self.dir, "tic", "SELECT 1", require=["id", "gaia"])
        self.assertEqual((names, rows), (["id", "gaia"], []))

    def test_mast_good_answer(self):
        tap.MAST_TIC_TAP = self.url("/votable_ok")
        names, rows, _ = tap.mast_query(self.dir, "tic", "SELECT 1", require=["id", "gaia"])
        self.assertEqual(names, ["id", "gaia", "pmra"])
        self.assertEqual(len(rows), 2)

    def test_csv_query_parses(self):
        names, rows, _ = tap.csv_query(self.dir, "k", self.url(), "SELECT 1")
        self.assertEqual((names, rows), (["a", "b"], [["1", "2"]]))


if __name__ == "__main__":
    unittest.main()
